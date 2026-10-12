#!/usr/bin/env python3
"""Run full pipeline test: sim -> analyzer -> llm -> tts -> queue."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.audio_queue import PriorityAudioQueue
from src.event_analyzer import GreetingBatcher, analyze
from src.tts_client import synthesize


def generate_sample_events() -> list[dict]:
    return [
        {"kind": "join", "user": "user_lan", "timestamp": 1},
        {"kind": "join", "user": "user_hung", "timestamp": 2},
        {"kind": "chat", "user": "user_lan", "text": "Shop ơi áo thun có size L không?"},
        {"kind": "gift", "user": "user_mai", "gift": "Hoa hồng"},
        {"kind": "chat", "user": "user_tuan", "text": "Kem dưỡng da dùng ban ngày được không shop?"},
        {"kind": "order", "user": "user_hong", "order_id": "ORD001"},
        {"kind": "join", "user": "user_quang", "timestamp": 3},
        {"kind": "chat", "user": "user_nam", "text": "Cho mình hỏi giá sản phẩm này bao nhiêu?"},
        {"kind": "gift", "user": "user_binh", "gift": "Tim bay"},
        {"kind": "chat", "user": "user_chi", "text": "Tai nghe bluetooth pin được bao lâu shop?"},
        {"kind": "order", "user": "user_mai", "order_id": "ORD002"},
        {"kind": "join", "user": "user_ngoc", "timestamp": 4},
        {"kind": "join", "user": "user_yen", "timestamp": 5},
        {"kind": "chat", "user": "user_hoa", "text": "Áo thun có những màu nào vậy ạ?"},
        {"kind": "chat", "user": "user_kien", "text": "Kem dưỡng có trắng da không shop?"},
        {"kind": "gift", "user": "user_yen", "gift": "Siêu xe"},
        {"kind": "chat", "user": "user_duong", "text": "Tai nghe có chống ồn chủ động không?"},
        {"kind": "order", "user": "user_quang", "order_id": "ORD003"},
        {"kind": "join", "user": "user_dat", "timestamp": 6},
        {"kind": "chat", "user": "user_dat", "text": "Chào shop, hôm nay có freeship không?"},
    ]


def main() -> int:
    events = generate_sample_events()
    queue = PriorityAudioQueue()
    processed_items: list[dict] = []

    print(f"=== PROCESSING {len(events)} SAMPLE EVENTS ===")

    for ev in events:
        analyzed = analyze(ev)
        speak_text = analyzed.get("speak_text")
        if speak_text:
            wav_path = synthesize(speak_text)
            queue.put(analyzed["kind"], analyzed["priority"], speak_text, str(wav_path))
            processed_items.append({**analyzed, "speak_text": speak_text, "wav": str(wav_path)})

    # Flush batcher con sot lai
    from src.event_analyzer import get_batcher
    final_greeting = get_batcher().flush()
    if final_greeting:
        analyzed = {"kind": "greeting", "priority": 3, "speak_text": final_greeting}
        wav_path = synthesize(analyzed["speak_text"])
        queue.put(analyzed["kind"], analyzed["priority"], analyzed["speak_text"], str(wav_path))
        processed_items.append({**analyzed, "wav": str(wav_path)})
    # In bang processed theo thu tu vao (enqueue)
    print("\n=== PIPELINE EXECUTION TABLE (ENQUEUED) ===")
    header = f"{'KIND':<10} | {'PRIORITY':<8} | {'SPEAK_TEXT':<65} | {'WAV'}"
    print(header)
    print("-" * len(header))
    for item in processed_items:
        text = (item["speak_text"][:62] + "...") if len(item["speak_text"]) > 65 else item["speak_text"]
        print(f"{item['kind']:<10} | {item['priority']:<8} | {text:<65} | {Path(item['wav']).name}")

    # Drain queue theo priority va in lai
    print(f"\n=== DRAIN QUEUE BY PRIORITY (QSIZE={queue.qsize()}) ===")
    drain_header = f"{'KIND':<10} | {'PRIORITY':<8} | {'SPEAK_TEXT':<65} | {'WAV'}"
    print(drain_header)
    print("-" * len(drain_header))
    while not queue.empty():
        item = queue.get()
        text = (item["speak_text"][:62] + "...") if len(item["speak_text"]) > 65 else item["speak_text"]
        print(f"{item['kind']:<10} | {item['priority']:<8} | {text:<65} | {Path(item['wav']).name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
