"""Client test: gui N event JSON that ve event bridge (ws://127.0.0.1:8765).

Vi du:
    python scripts/send_test_events.py                 # 3 event mac dinh
    python scripts/send_test_events.py --events 10      # 10 event (co gift/order/join/chat)
    python scripts/send_test_events.py --from-fixtures  # parse fixture DOM -> gui event that
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_EVENTS = [
    {"type": "join", "user": "Lan Anh"},
    {"type": "chat", "user": "Minh Tuấn", "text": "Áo thun cotton có size XL không shop?"},
    {"type": "gift", "user": "Thu Trang", "gift": "Hoa hồng", "count": 10},
]

EXTRA_EVENTS = [
    {"type": "order", "user": "Đức Huy", "product": "Tai nghe True Wireless Bass Boost", "amount": 450000},
    {"type": "chat", "user": "Phương Thảo", "text": "Có freeship không ạ?"},
    {"type": "gift", "user": "Văn Hậu", "gift": "Tên lửa", "count": 1},
    {"type": "join", "user": "Thanh Tùng"},
]


def build_events(count: int, from_fixtures: bool) -> list[dict]:
    if from_fixtures:
        from src.event_bridge import dom_to_events

        fixtures = ROOT / "tests" / "fixtures" / "raw_dom_samples"
        events: list[dict] = []
        for path in sorted(fixtures.glob("*.html")):
            events.extend(dom_to_events(path.read_text(encoding="utf-8"), source="fixture"))
        return events[:count] if count else events

    pool = DEFAULT_EVENTS + EXTRA_EVENTS
    return [dict(pool[i % len(pool)]) for i in range(count or len(DEFAULT_EVENTS))]


async def send(events: list[dict], uri: str) -> int:
    try:
        from websockets.asyncio.client import connect as _connect
    except ImportError:  # pragma: no cover
        from websockets import connect as _connect

    received: list[dict] = []
    async with _connect(uri, open_timeout=15) as conn:
        print(f"[client] ket noi {uri}", flush=True)
        for index, event in enumerate(events, 1):
            event.setdefault("ts", round(time.time(), 3))
            event["source"] = "send_test_events"
            await conn.send(json.dumps(event, ensure_ascii=False))
            print(f"[client] -> #{index} {json.dumps(event, ensure_ascii=False)}", flush=True)
            reply = json.loads(await asyncio.wait_for(conn.recv(), timeout=15))
            received.append(reply)
            print(f"[client] <- {json.dumps(reply, ensure_ascii=False)}", flush=True)

        await conn.send(json.dumps({"type": "ping"}))
        pong = json.loads(await asyncio.wait_for(conn.recv(), timeout=15))
        print(f"[client] <- {json.dumps(pong, ensure_ascii=False)}", flush=True)

    acks = [r for r in received if r.get("type") == "ack"]
    errors = [r for r in received if r.get("type") == "error"]
    print(f"\n[client] ack={len(acks)} error={len(errors)}", flush=True)
    if errors:
        for err in errors:
            print(f"[client] LOI: {err}", flush=True)
    return 0 if acks and not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Gui event JSON that ve event bridge")
    parser.add_argument("--uri", default="ws://127.0.0.1:8765")
    parser.add_argument("--events", type=int, default=0, help="so event can gui (0 = mac dinh)")
    parser.add_argument("--from-fixtures", action="store_true", help="lay event tu fixture DOM")
    parser.add_argument("--delay", type=float, default=0.0, help="nghi giua cac event (giay)")
    args = parser.parse_args()

    events = build_events(args.events, args.from_fixtures)
    if args.delay:
        events = [{"__delay__": args.delay, **e} for e in events]

    async def run() -> int:
        delay = args.delay
        if delay:
            events_clean = [{k: v for k, v in e.items() if k != "__delay__"} for e in events]
            try:
                from websockets.asyncio.client import connect as _connect
            except ImportError:  # pragma: no cover
                from websockets import connect as _connect
            acks = 0
            async with _connect(args.uri, open_timeout=15) as conn:
                for index, event in enumerate(events_clean, 1):
                    event.setdefault("ts", round(time.time(), 3))
                    event["source"] = "send_test_events"
                    await conn.send(json.dumps(event, ensure_ascii=False))
                    reply = json.loads(await asyncio.wait_for(conn.recv(), timeout=15))
                    print(f"[client] #{index} -> {json.dumps(event, ensure_ascii=False)}", flush=True)
                    print(f"[client]      <- {json.dumps(reply, ensure_ascii=False)}", flush=True)
                    acks += reply.get("type") == "ack"
                    await asyncio.sleep(delay)
            return 0 if acks == len(events_clean) else 1
        return await send(events, args.uri)

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
