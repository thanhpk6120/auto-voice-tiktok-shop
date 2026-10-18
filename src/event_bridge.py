"""Event bridge: hub WebSocket trung chuyen event (extension TikTok -> app).

Chay bridge:  python src/event_bridge.py serve --port 8765 [--sim] [--speed 1.0]

Hai vai tro tren cung endpoint `/ws`:
  - `?role=source` : extension / ui/index.html gui event JSON len bridge.
  - `?role=app`    : app.py (`run`, `doctor`) nhan event tu bridge.

ponytail: 1 hub in-process, khong auth, khong persist. Nang cap: token auth + Redis
pub/sub khi can nhieu app consumer hoac chay bridge khac may.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import queue
import re
import sys
import threading
import time
from collections import Counter
from html.parser import HTMLParser

# Ensure src is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_BRIDGE_URL = os.getenv("BRIDGE_URL", "ws://127.0.0.1:8765/ws?role=app")
_VALID_TYPES = {"join", "joined", "greeting", "chat", "comment", "message", "gift", "order"}


class Hub:
    """Fan-in event tu cac source -> hang doi cho consumer."""

    def __init__(self, maxsize: int = 1000):
        self.q: "queue.Queue[dict]" = queue.Queue(maxsize=maxsize)
        self.sources = 0
        self.received = 0
        self._lock = threading.Lock()

    def feed(self, event: dict) -> None:
        with self._lock:
            self.received += 1
        try:
            self.q.put_nowait(event)
        except queue.Full:
            pass  # ponytail: bo event khi nghen; nang cap: backpressure len extension

    def next_event(self, timeout: float):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None


def normalize(raw) -> dict | None:
    """Chuan hoa message tu extension/ui/simulator ve event dict hop le."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    ev = dict(raw)
    typ = str(ev.get("type") or ev.get("kind") or "").lower()
    if typ not in _VALID_TYPES:
        return None
    ev["type"] = typ
    ev.setdefault("ts", time.time())
    return ev


# --------------------------------------------------------------------------
# PHAN 1: PARSE DOM DASHBOARD -> EVENT (ban tham chieu cho extension/content.js)
# --------------------------------------------------------------------------

_ROW_TOKENS = {
    "comment", "comment-item", "commentitem", "chat", "chat-item", "chatitem",
    "chat-message", "chatmessage", "message", "message-item", "danmaku",
    "danmaku-item", "gift", "gift-item", "order", "order-item", "live-message",
    "barrage-item",
}
_ROW_SUBSTR = ("comment-item", "chat-item", "chat-line", "message-item", "danmaku", "barrage")
_ATTR_USER = ("data-user", "data-nickname", "data-username", "data-nick-name")
_ATTR_EVENT = ("data-event", "data-event-type", "data-type", "data-msg-type", "data-e2e")

_TYPE_ALIASES = {
    "joined": "join", "enter": "join", "member": "join", "greeting": "join",
    "comment": "chat", "message": "chat", "danmaku": "chat",
    "thanks": "gift", "purchase": "order", "paid": "order",
}
_ALIAS_KEYS = {
    "type": ("type", "kind", "event", "event_type", "eventType"),
    "user": ("user", "username", "nickname", "nick_name", "display_name", "displayName"),
    "text": ("text", "message", "content", "comment"),
    "gift": ("gift", "gift_name", "giftName", "gift_id", "giftId"),
    "count": ("count", "gift_count", "giftCount", "quantity", "qty"),
    "product": ("product", "product_name", "productName", "item", "title"),
    "amount": ("amount", "price", "total", "value"),
    "ts": ("ts", "timestamp", "time", "created_at", "createdAt"),
}
SCHEMA_TYPES = ("join", "chat", "gift", "order", "viewing_product")
SCHEMA_KEYS = ("type", "user", "ts", "text", "gift", "count", "product", "amount", "source")

_JOIN_RE = re.compile(
    r"^(?P<user>[^:：]{1,40}?)\s+(?:đã tham gia|vừa tham gia|vào phòng|đã vào|joined|has joined)\b",
    re.I)
_ORDER_RE = re.compile(
    r"^(?P<user>[^:：]{1,40}?)\s+(?:đã đặt đơn|đã chốt đơn|vừa chốt đơn|vừa đặt hàng|đã mua|"
    r"placed an order|ordered|purchased)\b(?P<rest>.*)$", re.I)
_GIFT_RE = re.compile(
    r"^(?P<user>[^:：]{1,40}?)\s+(?:đã tặng|vừa tặng|sent|tặng)\s+(?P<gift>.+?)"
    r"(?:\s*[x×*]\s*(?P<count>\d+))?\s*$", re.I)
_CHAT_RE = re.compile(r"^(?P<user>[^:：]{1,40}?)\s*[:：]\s*(?P<text>.+)$")
_AMOUNT_RE = re.compile(r"(\d[\d.,]{2,})")
_VIEW_RE = re.compile(
    r"^(?P<user>[^:：]{1,40}?)\s+(?:đang xem sản phẩm|đang xem|bấm xem|is viewing product|is viewing)\b(?P<product>.*)$",
    re.I,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).strip(" -–—|:")


def _pick(raw: dict, field: str):
    for key in _ALIAS_KEYS[field]:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _as_float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _as_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize_event(raw) -> dict:
    """Validate + chuan hoa 1 event tho thanh dung schema. Raise ValueError neu sai."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, dict):
        raise ValueError("event phai la object JSON")

    raw_type = _pick(raw, "type")
    if raw_type is None:
        raise ValueError("thieu field type")
    ev_type = str(raw_type).strip().lower()
    ev_type = _TYPE_ALIASES.get(ev_type, ev_type)
    if ev_type not in SCHEMA_TYPES:
        raise ValueError(f"type khong hop le: {raw_type!r} (cho phep: {', '.join(SCHEMA_TYPES)})")

    user = str(_pick(raw, "user") or "").strip()
    if not user:
        raise ValueError("thieu field user")

    event: dict = {"type": ev_type, "user": user, "ts": _as_float(_pick(raw, "ts")) or time.time()}

    text = _pick(raw, "text")
    if text is not None:
        text = str(text).strip()
        if text:
            event["text"] = text
    if ev_type == "chat" and not event.get("text"):
        raise ValueError("event chat thieu field text")

    if ev_type == "gift":
        event["gift"] = str(_pick(raw, "gift") or "quà").strip() or "quà"
        count = _as_int(_pick(raw, "count"))
        event["count"] = count if count and count > 0 else 1

    if ev_type in ("order", "viewing_product"):
        product = _pick(raw, "product")
        if product:
            event["product"] = str(product).strip()
        amount = _as_int(_pick(raw, "amount"))
        if amount is not None and amount >= 0:
            event["amount"] = amount
    if raw.get("source"):
        event["source"] = str(raw["source"])[:32]
    return event


def _parse_gift_text(line: str) -> tuple[str, int] | None:
    m = _GIFT_RE.match(_clean(line))
    if not m:
        return None
    return _clean(m.group("gift")), int(m.group("count")) if m.group("count") else 1


def _parse_order_text(line: str) -> tuple[str | None, int | None]:
    line = _clean(line)
    amount = _AMOUNT_RE.search(line)
    value = None
    if amount:
        value = int(re.sub(r"[.,]", "", amount.group(1)))
        line = _clean(line.replace(amount.group(1), ""))
    product = _clean(re.sub(r"^(for|của|sản phẩm|đơn|order)\s+", "", line, flags=re.I))
    product = _clean(re.sub(r"(đ|vnd|₫)$", "", product, flags=re.I))
    return (product or None), value


def classify_line(line: str) -> dict | None:
    """Doan 1 dong text cua khung chat thanh event. None neu khong nhan dang duoc."""
    line = _clean(line)
    if not line:
        return None

    m = _JOIN_RE.match(line)
    if m:
        return {"type": "join", "user": _clean(m.group("user"))}

    m = _ORDER_RE.match(line)
    if m:
        event = {"type": "order", "user": _clean(m.group("user"))}
        product, amount = _parse_order_text(m.group("rest"))
        if product:
            event["product"] = product
        if amount is not None:
            event["amount"] = amount
        return event

    m = _VIEW_RE.match(line)
    if m:
        prod = _clean(m.group("product"))
        return {
            "type": "viewing_product",
            "user": _clean(m.group("user")),
            "product": prod or "sản phẩm trên live",
            "text": line,
        }

    m = _GIFT_RE.match(line)
    if m:
        return {
            "type": "gift",
            "user": _clean(m.group("user")),
            "gift": _clean(m.group("gift")),
            "count": int(m.group("count")) if m.group("count") else 1,
        }

    m = _CHAT_RE.match(line)
    if m:
        text = _clean(m.group("text"))
        if text:
            return {"type": "chat", "user": _clean(m.group("user")), "text": text}
    return None


def _row_kind(tag: str, attrs: dict) -> str | None:
    """Doan loai event tu attribute (tin hieu manh nhat). 'row' = chi biet la 1 dong chat."""
    for key in _ATTR_EVENT:
        value = str(attrs.get(key) or "").lower()
        if not value:
            continue
        for alias, ev_type in _TYPE_ALIASES.items():
            if alias in value:
                return ev_type
        for token in ("gift", "order", "chat", "comment", "message", "join", "danmaku"):
            if token in value:
                return _TYPE_ALIASES.get(token, token)
    tokens = [t for t in re.split(r"[^a-z0-9-]+", str(attrs.get("class") or "").lower()) if t]
    for token in tokens:
        if token in _ROW_TOKENS or any(sub in token for sub in _ROW_SUBSTR):
            if "gift" in token:
                return "gift"
            if "order" in token:
                return "order"
            return "row"
    if str(attrs.get("role") or "").lower() in ("listitem", "row"):
        return "row"
    return None


def _attr_event(attrs: dict, chunks: list[str]) -> dict | None:
    """Dung attrs (data-*) lam tin hieu chinh, fallback sang text chunks."""
    kind = _row_kind(str(attrs.get("_tag") or ""), attrs)
    if not kind:
        return None
    if kind == "row":
        kind = "chat"

    joined = _clean(" ".join(chunks))
    text_chunks = None
    classified = classify_line(joined)
    if kind == "chat" and classified and classified["type"] != "chat":
        return classified  # text khop ro join/gift/order -> tin text hon class

    user = ""
    for key in _ATTR_USER:
        if attrs.get(key):
            user = _clean(str(attrs[key]))
            break
    if not user and len(chunks) >= 2 and len(_clean(chunks[0])) <= 40 and ":" not in _clean(chunks[0]):
        user, text_chunks = _clean(chunks[0]), _clean(" ".join(chunks[1:]))
    if not user:
        if classified:
            return classified
        m = _JOIN_RE.match(joined) or _ORDER_RE.match(joined) or _GIFT_RE.match(joined) or _CHAT_RE.match(joined)
        if m:
            user = _clean(m.group("user"))
    if not user:
        return None

    event: dict = {"type": kind, "user": user}
    if kind == "chat":
        text = text_chunks if text_chunks is not None else _clean(
            re.sub(r"^" + re.escape(user) + r"\s*[:：]?\s*", "", joined))
        if not text:
            return None
        event["text"] = text
    elif kind == "gift":
        gift_name = _clean(str(attrs.get("data-gift-name") or attrs.get("data-gift") or ""))
        count = _as_int(attrs.get("data-count") or attrs.get("data-gift-count"))
        from_text = _parse_gift_text(joined)
        if not gift_name and from_text:
            gift_name, count = from_text
        event["gift"] = gift_name or "quà"
        event["count"] = count if count and count > 0 else 1
    elif kind == "order":
        product = _clean(str(attrs.get("data-product") or attrs.get("data-product-name") or ""))
        amount = _as_int(attrs.get("data-amount") or attrs.get("data-price"))
        if not product or amount is None:
            text_product, text_amount = _parse_order_text(joined)
            product = product or text_product or ""
            amount = amount if amount is not None else text_amount
        if product:
            event["product"] = product
        if amount is not None and amount >= 0:
            event["amount"] = amount
    return event


class _RowExtractor(HTMLParser):
    """Boc text cua tung dong chat trong HTML dashboard (selector mem deo)."""

    _VOID = ("img", "input", "meta", "link", "source", "iframe", "embed")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[dict, list[str]]] = []
        self._depth = 0
        self._attrs: dict = {}
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "hr"):
            if self._depth:
                self._chunks.append("\n")
            return
        if tag in self._VOID:
            return
        attr_map = {k: v for k, v in attrs if v is not None}
        attr_map["_tag"] = tag
        if self._depth:
            self._depth += 1
            return
        if _row_kind(tag, attr_map):
            self._depth = 1
            self._attrs = attr_map
            self._chunks = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self._depth:
            self._chunks.append(data)

    def handle_endtag(self, tag):
        if not self._depth:
            return
        self._depth -= 1
        if self._depth == 0:
            self.rows.append((self._attrs, self._chunks))
            self._attrs, self._chunks = {}, []


def parse_rows(html: str) -> list[tuple[dict, list[str]]]:
    """-> [(attrs, chunks)] ; khong tim thay container nao thi tach theo dong text."""
    parser = _RowExtractor()
    parser.feed(html or "")
    parser.close()
    if parser.rows:
        return parser.rows
    text = re.sub(r"<[^>]+>", "\n", html or "")
    return [({}, [line]) for line in text.splitlines() if _clean(line)]


def dom_to_events(html: str, source: str = "dom") -> list[dict]:
    """Parse HTML khung chat -> list event dung schema (bo qua dong khong nhan dang duoc)."""
    events: list[dict] = []
    seen: set[tuple] = set()
    for attrs, chunks in parse_rows(html):
        chunks = [c for c in (chunk.strip() for chunk in chunks) if c]
        event = _attr_event(attrs, chunks) or classify_line(" ".join(chunks))
        if not event:
            continue
        event.setdefault("ts", time.time())
        event["source"] = source
        try:
            event = normalize_event(event)
        except ValueError:
            continue
        fingerprint = (
            event["type"], event["user"],
            event.get("text") or event.get("gift") or event.get("product"),
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        events.append(event)
    return events


# --------------------------------------------------------------------------
# PHAN 2: ASYNCIO EVENT BRIDGE (ws://127.0.0.1:8765) + heartbeat + log theo type
# --------------------------------------------------------------------------

DEFAULT_HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("BRIDGE_PORT", "8765"))

try:  # websockets >= 14
    from websockets.asyncio.server import serve as _async_serve
except ImportError:  # pragma: no cover
    try:
        from websockets import serve as _async_serve
    except ImportError:  # pragma: no cover
        _async_serve = None

log = logging.getLogger("event_bridge")


class EventBridge:
    """WebSocket server local -> asyncio.Queue event da validate."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, maxsize: int = 2000):
        self.host = host
        self.port = port
        self.queue: "asyncio.Queue[dict]" = asyncio.Queue(maxsize=maxsize)
        self.counts: Counter = Counter()
        self.clients = 0
        self.dropped = 0
        self.invalid = 0
        self.started_at: float | None = None
        # client role=app (app.py `run`/`doctor`) dang cho nhan event
        self._apps: set = set()
        self._app_lock = asyncio.Lock()

    @property
    def received(self) -> int:
        return sum(self.counts.values())

    def stats(self) -> dict:
        return {
            "received": self.received,
            "by_type": dict(self.counts),
            "invalid": self.invalid,
            "dropped": self.dropped,
            "clients": self.clients,
        }

    async def drain(self) -> dict:
        return await self.queue.get()

    async def _broadcast(self, event: dict) -> None:
        """Day event da validate toi moi client role=app (app.py run/doctor)."""
        async with self._app_lock:
            apps = list(self._apps)
        if not apps:
            return
        payload = json.dumps(event, ensure_ascii=False)
        dead = []
        for conn in apps:
            try:
                await conn.send(payload)
            except Exception:
                dead.append(conn)
        if dead:
            async with self._app_lock:
                for conn in dead:
                    self._apps.discard(conn)

    async def _send(self, conn, payload: dict) -> None:
        try:
            await conn.send(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:  # client da ngat
            log.debug("send failed: %s", exc)

    async def _accept(self, event: dict) -> None:
        self.counts[event["type"]] += 1
        if self.queue.full():
            self.dropped += 1
            log.warning("queue day, drop event %s", event["type"])
        else:
            await self.queue.put(event)
        await self._broadcast(event)

    async def handler(self, conn, path: str | None = None) -> None:
        # ponytail: (conn, path=None) de chay ca websockets >=14 lan legacy
        self.clients += 1
        role = ""
        if path and "role=" in path:
            role = path.split("role=", 1)[1].split("&", 1)[0]
        log.info("client ket noi: %s role=%s", getattr(conn, "remote_address", "?"), role or "source")

        if role == "app":
            # consumer: nhan moi event da validate (khong gui nguoc len)
            async with self._app_lock:
                self._apps.add(conn)
            try:
                async for _ in conn:  # bo qua input, giu ket noi mo
                    pass
            except Exception:
                pass
            finally:
                async with self._app_lock:
                    self._apps.discard(conn)
                self.clients -= 1
                log.info("app client ngat ket noi")
            return

        try:
            async for message in conn:
                if isinstance(message, (bytes, bytearray)):
                    try:
                        message = message.decode("utf-8")
                    except UnicodeDecodeError:
                        self.invalid += 1
                        await self._send(conn, {"type": "error", "error": "payload khong phai UTF-8"})
                        continue
                try:
                    payload = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    self.invalid += 1
                    await self._send(conn, {"type": "error", "error": "JSON khong hop le"})
                    continue

                if isinstance(payload, dict) and str(payload.get("type", "")).lower() == "ping":
                    await self._send(conn, {"type": "pong", "ts": time.time()})
                    continue

                batch = payload.get("events") if isinstance(payload, dict) else None
                items = batch if isinstance(batch, list) else [payload]
                acked: list[str] = []
                for item in items:
                    try:
                        event = normalize_event(item)
                    except ValueError as exc:
                        self.invalid += 1
                        log.warning("event sai schema: %s (%s)", exc, item)
                        await self._send(conn, {"type": "error", "error": str(exc)})
                        continue
                    await self._accept(event)
                    acked.append(event["type"])
                    log.info("event #%d type=%s user=%s", self.received, event["type"], event["user"])
                if acked:
                    await self._send(conn, {
                        "type": "ack",
                        "seq": self.received,
                        "events": acked,
                        "counts": dict(self.counts),
                    })
        except Exception as exc:  # pragma: no cover - loi mang
            log.warning("client loi: %s", exc)
        finally:
            self.clients -= 1
            log.info("client ngat ket noi")

    async def serve_forever(self) -> None:
        if _async_serve is None:
            raise RuntimeError("thieu thu vien websockets: pip install websockets")
        self.started_at = time.time()
        async with _async_serve(
            self.handler, self.host, self.port,
            ping_interval=20, ping_timeout=20, max_queue=64,
        ):
            log.info("Event bridge nghe tai ws://%s:%d", self.host, self.port)
            await asyncio.Future()  # chay mai den khi bi cancel


async def run_bridge(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, on_event=None,
                     duration: float | None = None) -> EventBridge:
    """Chay server + vong lap consume event. `duration` (giay) cho kich ban test."""
    bridge = EventBridge(host, port)
    server_task = asyncio.create_task(bridge.serve_forever())

    async def consume():
        while True:
            event = await bridge.drain()
            event["_seq"] = bridge.received
            if on_event:
                on_event(event)

    consumer_task = asyncio.create_task(consume())
    try:
        if duration:
            await asyncio.sleep(duration)
        else:
            await server_task
    finally:
        consumer_task.cancel()
        server_task.cancel()
        await asyncio.gather(consumer_task, server_task, return_exceptions=True)
    return bridge


# ---------- Server (legacy hub in-process) ----------

def _role(ws) -> str:
    req = getattr(ws, "request", None)
    path = getattr(req, "path", "") or ""
    if "role=" in path:
        return path.split("role=", 1)[1].split("&", 1)[0]
    return "app"


def _sim_producer(hub: Hub, stop: threading.Event, speed: float = 1.0, seed: int = 42) -> None:
    from event_simulator import iter_events

    gen = iter_events(seed=seed)
    prev_ts = None
    for ev in gen:
        if stop.is_set():
            return
        ts = ev.get("ts")
        if prev_ts is not None and ts is not None:
            time.sleep(max(0.0, (ts - prev_ts)) * speed)
        prev_ts = ts
        hub.feed(ev)


def serve(host: str = "127.0.0.1", port: int = 8765, sim: bool = False, speed: float = 1.0,
          stop: threading.Event | None = None) -> threading.Event:
    """Chay bridge trong thread nen; tra ve stop_event de dung."""
    from websockets.sync.server import serve as ws_serve

    hub = Hub()
    stop = stop or threading.Event()

    def handler(ws):
        role = _role(ws)
        if role == "source":
            hub.sources += 1
            try:
                for msg in ws:
                    ev = normalize(msg)
                    if ev is not None:
                        hub.feed(ev)
            except Exception:
                pass
            finally:
                hub.sources -= 1
            return
        # role=app: day event ra consumer
        try:
            while not stop.is_set():
                ev = hub.next_event(timeout=0.5)
                if ev is None:
                    continue
                ws.send(json.dumps(ev, ensure_ascii=False))
        except Exception:
            pass

    server = ws_serve(handler, host, port)
    t = threading.Thread(target=server.serve_forever, name="event-bridge", daemon=True)
    t.start()
    if sim:
        threading.Thread(target=_sim_producer, args=(hub, stop, speed), name="bridge-sim", daemon=True).start()
    return stop


# ---------- Client ----------

def iter_events(url: str = DEFAULT_BRIDGE_URL, stop_event: threading.Event | None = None,
                open_timeout: float = 5.0, recv_timeout: float = 0.5):
    """Generator nhan event tu bridge (dung cho app.py `run` / `doctor`)."""
    from websockets.sync.client import connect

    with connect(url, open_timeout=open_timeout) as ws:
        while not (stop_event is not None and stop_event.is_set()):
            try:
                msg = ws.recv(timeout=recv_timeout)
            except TimeoutError:
                continue
            ev = normalize(msg)
            if ev is not None:
                yield ev


def main() -> int:
    parser = argparse.ArgumentParser(description="Event bridge (TikTok extension -> app)")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("serve", help="Chay bridge WebSocket")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sim", action="store_true", help="Tu sinh event gia lap (khong can extension)")
    p.add_argument("--speed", type=float, default=1.0, help="He so toc do cho --sim")
    sub.add_parser("health", help="Kiem tra bridge co song khong")
    args = parser.parse_args()

    if args.command == "health":
        try:
            for _ in iter_events(open_timeout=3.0, recv_timeout=0.5):
                print("[BRIDGE] OK (nhan duoc event)")
                return 0
        except Exception as e:
            print(f"[BRIDGE] FAIL {e}", file=sys.stderr)
            return 1

    if args.command != "serve":
        parser.print_help()
        return 0

    stop = serve(host=args.host, port=args.port, sim=args.sim, speed=args.speed)
    print(f"[BRIDGE] ws://{args.host}:{args.port}/ws  (role=source | role=app)"
          f"{'  +sim' if args.sim else ''}  Ctrl+C de dung")
    try:
        while not stop.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
    finally:
        print("[BRIDGE] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
