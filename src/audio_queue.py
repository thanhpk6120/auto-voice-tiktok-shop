"""Hàng đợi audio ưu tiên (gift/order p1 trước chat p2, greeting p3)."""
from __future__ import annotations

import itertools
import queue


class PriorityAudioQueue:
    """Wrapper quanh queue.PriorityQueue với counter chống trùng priority."""

    def __init__(self):
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._counter = itertools.count()

    def put(self, kind, priority, speak_text, wav) -> bool:
        if self.qsize() > 50 and (priority == 3 or kind == "greeting"):
            return False
        payload = {"kind": kind, "priority": priority, "speak_text": speak_text, "wav": wav}
        self._q.put((priority, next(self._counter), payload))
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
