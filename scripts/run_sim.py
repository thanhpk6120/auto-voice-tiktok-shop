import itertools
import json
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.event_simulator import iter_events


def main(n: int = 20, seed: int = 42) -> int:
    out_path = root_dir / "data" / "sample-events.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    events = list(itertools.islice(iter_events(seed=seed), n))
    with open(out_path, "w", encoding="utf-8") as f:
        for ev in events:
            line = json.dumps(ev, ensure_ascii=False)
            print(line)
            f.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
