"""E2E that: bridge rieng (port rieng) + client role=source + app.py run -> bang chung chay that.

Chay: python scripts/e2e_bridge_run.py
Tu mo bridge o port 8801 (khong dung bridge ngoai), gui event nhu extension/ui, roi chay app.py run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

os.environ["BRIDGE_PORT"] = "8801"
import event_bridge as eb  # noqa: E402

PORT = 8801
URL = f"ws://127.0.0.1:{PORT}/ws?role=app"
SRC_URL = f"ws://127.0.0.1:{PORT}/ws?role=source"

EVENTS = [
    {"type": "join", "user": "Lan Anh"},
    {"type": "join", "user": "Minh Tuấn"},
    {"type": "chat", "user": "Thu Trang", "text": "Áo thun cotton có size XL không shop?"},
    {"type": "gift", "user": "Hoàng Nam", "gift": "Hoa hồng", "count": 10},
    {"type": "order", "user": "Đức Huy", "product": "Tai nghe True Wireless Bass Boost", "amount": 450000},
    {"type": "chat", "user": "Phương Thảo", "text": "Có freeship không ạ?"},
]


def main() -> int:
    ap = argparse.ArgumentParser(description="E2E that qua bridge (tu mo bridge port rieng)")
    ap.add_argument("--play", action="store_true", help="phat tieng that ra loa (bo --no-play)")
    ap.add_argument("--max-events", type=int, default=len(EVENTS), help="so event gui tu role=source")
    args = ap.parse_args()
    events = EVENTS[: args.max_events]

    from websockets.sync.client import connect

    stop = eb.serve(host="127.0.0.1", port=PORT, sim=False, stop=threading.Event())
    print(f"# bridge rieng: python src/event_bridge.py serve --port {PORT}  (= {eb.DEFAULT_BRIDGE_URL.replace('8765', str(PORT))})")
    time.sleep(1.0)

    env = dict(os.environ, BRIDGE_URL=URL)
    proc = subprocess.Popen(
        [sys.executable, "src/app.py", "run", *([] if args.play else ["--no-play"]),
         "--max-events", str(len(events))],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        cwd=str(ROOT), env=env,
    )
    time.sleep(6.0)

    with connect(SRC_URL, open_timeout=15) as ws:
        print(f"# [role=source] gui {len(events)} event (giong extension/ui/index.html)")
        for ev in events:
            ws.send(json.dumps({**ev, "ts": time.time()}, ensure_ascii=False))
            time.sleep(0.6)
        time.sleep(1.0)

    try:
        out, _ = proc.communicate(timeout=150)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
        print("# WARN: app.py khong tu dung, da kill")
    print(out)
    stop.set()
    print(f"# exit code app.py = {proc.returncode}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
