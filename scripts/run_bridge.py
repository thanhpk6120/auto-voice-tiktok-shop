"""Chay event bridge that: server WebSocket local + in ra event nhan duoc tu extension.

Vi du:
    python scripts/run_bridge.py                       # chay mai, Ctrl+C de dung
    python scripts/run_bridge.py --duration 30         # chay 30s (dung cho test tu dong)
    python scripts/run_bridge.py --analyze             # in them kind/speak_text tu event_analyzer
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.event_bridge import DEFAULT_HOST, DEFAULT_PORT, run_bridge  # noqa: E402


def _now() -> str:
    return time.strftime("%H:%M:%S")


def build_printer(analyze: bool):
    analyzer = None
    if analyze:
        from src.event_analyzer import analyze as analyzer  # noqa: E402

    def on_event(event: dict) -> None:
        payload = {k: v for k, v in event.items() if k != "ts"}
        print(f"[{_now()}] EVENT #{event.get('_seq', '?')} {json.dumps(payload, ensure_ascii=False)}", flush=True)
        if analyzer is not None:
            result = analyzer(event, use_batcher=False)
            print(
                f"           -> kind={result['kind']} priority={result['priority']} "
                f"speak={result['speak_text']!r}",
                flush=True,
            )

    return on_event


async def main_async(args) -> int:
    print(
        f"[bridge] nghe tai ws://{args.host}:{args.port} | duration={args.duration or 'vo han'} "
        f"| analyze={args.analyze}",
        flush=True,
    )

    bridge = await run_bridge(
        host=args.host,
        port=args.port,
        on_event=build_printer(args.analyze),
        duration=args.duration,
    )

    stats = bridge.stats()
    print("\n=== KET QUA PHIEN BRIDGE ===", flush=True)
    print(f"received={stats['received']} invalid={stats['invalid']} dropped={stats['dropped']}", flush=True)
    print(f"by_type={json.dumps(stats['by_type'], ensure_ascii=False)}", flush=True)
    return 0 if stats["received"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Event bridge server (TikTok Shop LIVE -> local queue)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--duration", type=float, default=None, help="tu dong dung sau N giay")
    parser.add_argument("--analyze", action="store_true", help="in them ket qua event_analyzer")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n[bridge] dung theo yeu cau (Ctrl+C)", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
