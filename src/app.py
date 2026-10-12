import argparse
import sys
import time
import os

# Ensure src is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from event_analyzer import analyze
from tts_client import synthesize
from audio_queue import PriorityAudioQueue
from event_simulator import iter_events

def process_event(event, queue):
    res = analyze(event)
    speak_text = res.get("speak_text")
    if speak_text:
        wav = synthesize(speak_text)
        kind = res.get("kind", "unknown")
        priority = res.get("priority", 3)
        queue.put(kind, priority, speak_text, wav)
        print(f"event={event.get('type', event.get('kind', ''))} → speak_text='{speak_text}' → wav={wav} → queue-size={queue.qsize()}")

def handle_simulate():
    print("Starting simulation...")
    queue = PriorityAudioQueue()
    gen = iter_events(seed=42)
    # Lấy 10 sự kiện (4 join batch + vài cái sau)
    events = [next(gen) for _ in range(10)]
    for e in events:
        process_event(e, queue)
    # Force flush batch nếu còn
    from event_analyzer import get_batcher
    batched = get_batcher().flush()
    if batched:
        wav = synthesize(batched)
        queue.put("greeting", 3, batched, wav)
        print(f"event=join(flushed) → speak_text='{batched}' → wav={wav} → queue-size={queue.qsize()}")
        
    print("Simulation done.")

def handle_live():
    print("Live mode not fully implemented yet.")

def handle_stop():
    print("Stopping app...")

def main():
    parser = argparse.ArgumentParser(description="Auto Voice TikTok Shop LIVE CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("simulate", help="Simulate events")
    subparsers.add_parser("live", help="Start live mode")
    subparsers.add_parser("stop", help="Stop app")
    
    args = parser.parse_args()
    
    if args.command == "simulate":
        handle_simulate()
    elif args.command == "live":
        handle_live()
    elif args.command == "stop":
        handle_stop()
        sys.exit(0)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
