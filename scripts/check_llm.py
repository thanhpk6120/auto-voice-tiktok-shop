import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.config import LLM_BASE_URL, LLM_MODEL
from src.llm_client import chat


def main():
    print(f"[INFO] Checking LLM endpoint: {LLM_BASE_URL} with model: {LLM_MODEL}")
    system_prompt = "You are a concise AI assistant for TikTok live stream sales."
    user_prompt = "Chào bạn! Hãy giới thiệu bạn là ai trong đúng 1 câu ngắn gọn."

    try:
        reply = chat(system=system_prompt, user=user_prompt, model=LLM_MODEL, timeout=20.0)
        print("[STATUS] OK")
        print(f"[SAMPLE_RESPONSE] {reply}")
        return 0
    except Exception as e:
        print("[STATUS] FAIL", file=sys.stderr)
        print(f"[ERROR] LLM check failed (server offline or unreachable): {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    sys.exit(main() or 0)

# ponytail: simple check script; extend with latency benchmark if needed
