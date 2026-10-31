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
    """Hàng đợi âm thanh ưu tiên theo luồng trượt realtime:
    - Mỗi loại sự kiện (kind: order, gift, sales, greeting, auto_pitch...) chỉ giữ tối đa `max_per_kind` câu (mặc định 3).
    - Khi có câu mới cùng loại mà đã đủ 3 câu: tự động bỏ câu CŨ NHẤT để ưu tiên câu MỚI NHẤT (cảm giác realtime).
    - Thứ tự lấy ra: Priority 1 (order/gift) -> Priority 2 (sales/chat) -> Priority 3 (greeting/auto_pitch).
    """

    def __init__(
        self,
        on_play=None,
        on_finish=None,
        dry_run: bool = False,
        queue_limit: int = 50,
        interrupt_mode: str = "finish",
        post_speech_padding_s: float = 0.35,
        max_per_kind: int = 3,
    ):
        self._counter = itertools.count()
        self._limit = max(5, int(queue_limit))
        self._max_per_kind = max(1, int(max_per_kind))
        self._on_play = on_play
        self._dry_run = dry_run or on_play is None
        self._on_finish = on_finish
        self.interrupt_mode = interrupt_mode
        self.post_speech_padding_s = max(0.05, float(post_speech_padding_s))
        self._stop = threading.Event()
        self._interrupt = threading.Event()
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._items: list[tuple[int, int, dict]] = []
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
        from pathlib import Path
        with self._lock:
            # 1. Giới hạn trượt theo từng loại (mỗi loại chỉ giữ tối đa max_per_kind voice, mặc định 3)
            matching_indices = [
                i for i, (_, _, p) in enumerate(self._items)
                if p.get("kind") == kind
            ]
            if len(matching_indices) >= self._max_per_kind:
                # Bỏ câu CŨ NHẤT của loại này (vị trí đầu tiên trong matching_indices)
                drop_idx = matching_indices[0]
                dropped_tuple = self._items.pop(drop_idx)
                dropped_item = dropped_tuple[2]
                self.stats["dropped_overflow"] += 1

                # Dọn file wav tạm nếu cần
                w = dropped_item.get("wav")
                if w:
                    try:
                        pw = Path(w)
                        if pw.is_file() and ("out" in pw.parts or "local_cache" in pw.parts or "pitch_" in pw.name):
                            pw.unlink()
                    except Exception:
                        pass

                old_txt = (dropped_item.get("speak_text") or "").strip().replace("\n", " ")[:40]
                print(
                    f"[queue] Hàng đợi loại '{kind}' đã đủ {self._max_per_kind} -> bỏ câu cũ nhất: '{old_txt}...' "
                    f"để ưu tiên realtime (queue-size={len(self._items)})",
                    flush=True,
                )

            # 2. Giới hạn trần tổng số lượng hàng đợi
            if len(self._items) >= self._limit and (priority == 3 or kind in ("greeting", "auto_pitch")):
                self.stats["dropped_overflow"] += 1
                return False

            payload = {"kind": kind, "priority": priority, "speak_text": speak_text, "wav": wav}
            seq = next(self._counter)
            self._items.append((priority, seq, payload))
            # Sắp xếp theo: priority tăng dần (1 trước 2 trước 3), seq tăng dần (FIFO trong cùng priority)
            self._items.sort(key=lambda x: (x[0], x[1]))
            self._cond.notify()

            if priority == INTERRUPT_PRIORITY:
                self._request_interrupt()
            return True

    def get(self, *args, **kwargs):
        import queue as _q
        with self._lock:
            timeout = kwargs.get("timeout", None)
            if not self._items:
                if kwargs.get("block", True) is False:
                    raise _q.Empty
                ok = self._cond.wait(timeout=timeout)
                if not ok or not self._items:
                    raise _q.Empty
            _, _, item = self._items.pop(0)
            return item

    def qsize(self) -> int:
        with self._lock:
            return len(self._items)

    def empty(self) -> bool:
        with self._lock:
            return len(self._items) == 0

    def current(self) -> dict | None:
        with self._lock:
            return self._current

    def is_playing(self) -> bool:
        with self._lock:
            return self._current is not None

    def is_idle(self) -> bool:
        with self._lock:
            return self._current is None and len(self._items) == 0

    # ---------- Worker ----------

    def start(self) -> "PriorityAudioQueue":
        if self._worker is None or not self._worker.is_alive():
            self._stop.clear()
            self._worker = threading.Thread(target=self._run, name="audio-queue-worker", daemon=True)
            self._worker.start()
        return self

    def stop(self, drain: bool = True, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._lock:
            self._cond.notify_all()
            if drain:
                self._items.clear()
        if self._worker is not None:
            self._worker.join(timeout=timeout)
            self._worker = None

    def _request_interrupt(self) -> None:
        """Item p1 vừa vào: ngắt item đang phát nếu mode là 'interrupt' và item là p2/p3."""
        if self._dry_run or self.interrupt_mode == "finish":
            return
        with self._lock:
            cur = self._current
            if cur is None or cur.get("priority", 3) <= INTERRUPT_PRIORITY:
                return
        self._interrupt.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                while not self._items and not self._stop.is_set():
                    self._cond.wait(timeout=0.2)
                if self._stop.is_set() and not self._items:
                    break
                if not self._items:
                    continue
                _, _, item = self._items.pop(0)
                self._current = item

            self._interrupt.clear()
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
                        with self._lock:
                            self._items.append((item.get("priority", 3), next(self._counter), item))
                            self._items.sort(key=lambda x: (x[0], x[1]))
                            self._cond.notify()
                    else:
                        self.stats["dropped_requeue"] += 1
            else:
                self.stats["played"] += 1
                print(f"[queue/stat] played={self.stats['played']} queue-size={self.qsize()}", flush=True)
            if self._on_finish is not None:
                try:
                    self._on_finish(item)
                except Exception:
                    pass
            # Khoảng nghỉ tự nhiên sau phát để không bị ngắt chữ cuối và xả sạch audio buffer
            pad = max(0.08, float(getattr(self, "post_speech_padding_s", 0.35)))
            time.sleep(pad)
            self._interrupt.clear()
