"""Hàng đợi audio ưu tiên (gift/order p1 trước chat p2, greeting p3) + worker thread phát audio.

Chính sách ngắt (interrupt_mode):
1. 'finish' (MẶC ĐỊNH): KHÔNG ngắt item đang phát. Khi có item ưu tiên cao (p1) vào hàng đợi,
   worker đợi câu hiện tại đọc xong trọn vẹn rồi mới phát item p1. Không bỏ bất kỳ item nào.
   Nếu item bị gián đoạn do lỗi/ngoại cảnh, item được đẩy lại vào hàng đợi (tối đa 2 lần).
   Lý do chọn 'finish' làm mặc định: trong livestream bán hàng, việc ngắt ngang giữa câu
   khiến khách nghe bị cụt, mất tự nhiên và tạo trải nghiệm nghe khó chịu.
2. 'interrupt': Khi worker đang phát item priority > 1 (chat/greeting) mà có item priority == 1
   (gift/order) mới vào hàng đợi, item đang phát bị NGẮT và BỎ LUÔN (không phát lại sau),
   item p1 được phát ngay. Phù hợp khi cần phản hồi tức thì sự kiện quà tặng/đơn hàng.
"""
from __future__ import annotations

import itertools
import queue
import threading
import time
INTERRUPT_PRIORITY = 1


class PriorityAudioQueue:
    """Hàng đợi ưu tiên + worker thread tiêu thụ, gọi `on_play(wav, stop_event)`."""

    def __init__(
        self,
        on_play=None,
        on_finish=None,
        dry_run: bool = False,
        queue_limit: int = 50,
        interrupt_mode: str = "finish",
    ):
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._counter = itertools.count()
        self._limit = queue_limit
        self._on_play = on_play
        self._dry_run = dry_run or on_play is None
        self._on_finish = on_finish
        self.interrupt_mode = interrupt_mode
        self._stop = threading.Event()
        self._interrupt = threading.Event()
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._worker: threading.Thread | None = None
        self.stats = {
            "played": 0,
            "interrupted": 0,
            "dropped_overflow": 0,
            "errors": 0,
            "requeued": 0,
            "dropped_requeue": 0,
        }

    # ---------- API hàng đợi ----------

    def put(self, kind, priority, speak_text, wav) -> bool:
        if self.qsize() > self._limit and (priority == 3 or kind == "greeting"):
            self.stats["dropped_overflow"] += 1
            return False
        payload = {"kind": kind, "priority": priority, "speak_text": speak_text, "wav": wav}
        self._q.put((priority, next(self._counter), payload))
        if priority == INTERRUPT_PRIORITY:
            self._request_interrupt()
        return True

    def get(self, *args, **kwargs):
        item = self._q.get(*args, **kwargs)
        if isinstance(item, tuple) and len(item) == 3:
            return item[2]
        return item

    def qsize(self) -> int:
        return self._q.qsize()

    def empty(self) -> bool:
        return self._q.empty()

    def current(self) -> dict | None:
        with self._lock:
            return self._current

    def is_playing(self) -> bool:
        with self._lock:
            return self._current is not None

    def is_idle(self) -> bool:
        with self._lock:
            return self._current is None and self._q.empty()

    # ---------- Worker ----------

    def start(self) -> "PriorityAudioQueue":
        if self._worker is None or not self._worker.is_alive():
            self._stop.clear()
            self._worker = threading.Thread(target=self._run, name="audio-queue-worker", daemon=True)
            self._worker.start()
        return self

    def stop(self, drain: bool = True, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)
            self._worker = None
        if drain:
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break

    def _request_interrupt(self) -> None:
        """Item p1 vua vao: ngat item dang phat neu mode la 'interrupt' va item la p2/p3."""
        if self._dry_run or self.interrupt_mode == "finish":
            return
        with self._lock:
            cur = self._current
            if cur is None or cur.get("priority", 3) <= INTERRUPT_PRIORITY:
                return
        self._interrupt.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                _, _, item = self._q.get(timeout=0.2)
            except queue.Empty:
                continue

            self._interrupt.clear()
            with self._lock:
                self._current = item
            interrupted = False
            try:
                if not self._dry_run and self._on_play is not None:
                    ok = self._on_play(item.get("wav"), self._interrupt)
                    interrupted = ok is False or self._interrupt.is_set()
            except Exception:
                self.stats["errors"] += 1
                interrupted = False
            finally:
                with self._lock:
                    self._current = None

            if interrupted:
                self.stats["interrupted"] += 1
                if self.interrupt_mode == "interrupt":
                    pass
                else:
                    requeue_count = item.get("_requeue", 0)
                    if requeue_count < 2:
                        item["_requeue"] = requeue_count + 1
                        self.stats["requeued"] += 1
                        self._q.put((item.get("priority", 3), next(self._counter), item))
                    else:
                        self.stats["dropped_requeue"] += 1
            else:
                self.stats["played"] += 1
            if self._on_finish is not None:
                try:
                    self._on_finish(item)
                except Exception:
                    pass
            # Khoang nghi tu nhien giua 2 cau phat lien tiep
            time.sleep(0.08)
            self._interrupt.clear()
