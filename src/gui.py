"""GUI (tkinter) - cau hinh ket noi + Start/Stop + log realtime.

Mo bang: chay .exe khong tham so, hoac `python src/launcher.py` (khong tham so),
hoac truc tiep `python src/gui.py`.

Toan bo schema lay tu `settings.SECTIONS` / `DEFAULTS` / `SECRET_KEYS` nen them key
moi chi can sua settings.py. Logic thuan (build_form/coerce_value/device_spec/parse_event_line)
tach rieng de test khong can mainloop.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parent
for _p in (str(_SRC), str(_SRC.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import launcher  # noqa: E402
import settings  # noqa: E402

TITLE = "Auto Voice TikTok Shop - Cấu hình"
POLL_MS = 100


def child_cmd(extra: list[str]) -> list[str]:
    """Lenh spawn tien trinh con chay pipeline/doctor.

    Frozen: goi lai chinh .exe voi co `--internal` (launcher xu ly).
    Source : goi python + src/launcher.py --internal.
    KHONG dung `python -c <code>`: ban frozen la .exe nen `-c` bi PyInstaller bo qua.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--internal", *extra]
    import launcher as _launcher

    return [sys.executable, str(Path(_launcher.__file__).resolve()), "--internal", *extra]


try:
    import tkinter as tk
    from tkinter import scrolledtext, ttk

    TK_ERROR: str | None = None
except Exception as _e:  # pragma: no cover - may thieu tkinter / headless
    tk = None  # type: ignore
    ttk = None  # type: ignore
    scrolledtext = None  # type: ignore
    TK_ERROR = f"{type(_e).__name__}: {_e}"


# --------------------------- logic thuan (test duoc) ---------------------------

_RE_EVENT = re.compile(r"event=([^\s\-]+)")
_RE_SPEAK = re.compile(r"speak_text=(?:'([^']*)'|\"([^\"]*)\")")
_RE_PRIO = re.compile(r"priority=(\d+)")
_RE_QSIZE = re.compile(r"queue-size=(\d+)")


def parse_event_line(line: str) -> dict | None:
    """Parse 1 dong log chua thong tin event tu app.

    Nhan dien: event=<type>, speak_text='...', priority=<n>, queue-size=<n>.
    Tra dict {event, speak_text, priority, queue_size} hoac None neu khong khop.
    """
    if not line or "event=" not in line:
        return None
    m_ev = _RE_EVENT.search(line)
    if not m_ev:
        return None

    res: dict = {
        "event": m_ev.group(1),
        "speak_text": None,
        "priority": None,
        "queue_size": None,
    }
    m_sp = _RE_SPEAK.search(line)
    if m_sp:
        res["speak_text"] = m_sp.group(1) if m_sp.group(1) is not None else m_sp.group(2)

    m_pr = _RE_PRIO.search(line)
    if m_pr:
        res["priority"] = int(m_pr.group(1))

    m_qs = _RE_QSIZE.search(line)
    if m_qs:
        res["queue_size"] = int(m_qs.group(1))

    return res


class StatusCounters:
    """Bo dem thong ke trang thai tu stream log (doc lap voi tkinter)."""

    def __init__(self) -> None:
        self.events: dict[str, int] = {
            "join": 0,
            "chat": 0,
            "gift": 0,
            "order": 0,
        }
        self.queue_size: int = 0
        self.played: int = 0
        self.interrupted: int = 0
        self.dropped: int = 0
        self.total_events: int = 0

    def feed(self, line: str) -> dict | None:
        parsed = parse_event_line(line)
        if parsed is not None:
            raw_ev = parsed["event"]
            base_ev = raw_ev.split("(")[0].strip()
            self.events[base_ev] = self.events.get(base_ev, 0) + 1
            self.total_events += 1
            if parsed["queue_size"] is not None:
                self.queue_size = parsed["queue_size"]

        if any(k in line for k in ("played", "interrupted", "dropped")):
            self._parse_queue_stats(line)

        return parsed

    def _parse_queue_stats(self, line: str) -> None:
        m_played = re.search(r"(?:'|\")?played(?:'|\")?\s*[:=]\s*(\d+)", line)
        if m_played:
            self.played = int(m_played.group(1))

        m_intr = re.search(r"(?:'|\")?interrupted(?:'|\")?\s*[:=]\s*(\d+)", line)
        if m_intr:
            self.interrupted = int(m_intr.group(1))

        m_drop = re.search(r"(?:'|\")?dropped(?:_overflow)?(?:'|\")?\s*[:=]\s*(\d+)", line)
        if m_drop:
            self.dropped = int(m_drop.group(1))

    def reset(self) -> None:
        for k in list(self.events.keys()):
            self.events[k] = 0
        self.queue_size = 0
        self.played = 0
        self.interrupted = 0
        self.dropped = 0
        self.total_events = 0

    def snapshot(self) -> dict:
        return {
            "events": dict(self.events),
            "total_events": self.total_events,
            "queue_size": self.queue_size,
            "played": self.played,
            "interrupted": self.interrupted,
            "dropped": self.dropped,
        }


def field_kind(value) -> str:
    """Kieu widget theo gia tri dang co: bool -> Checkbutton, so -> Entry validate."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return "text"


def build_form(sections: dict, cfg: dict, secret_keys=()) -> list[dict]:
    """Spec cac dong form tu settings.SECTIONS. Tra [{'section', 'fields': [...]}]."""
    secrets = set(secret_keys)
    form = []
    for section_name, keys in sections.items():
        fields = []
        for k in keys:
            val = cfg.get(k)
            fields.append(
                {
                    "key": k,
                    "value": val,
                    "kind": field_kind(val),
                    "secret": k in secrets,
                }
            )
        form.append({"section": section_name, "fields": fields})
    return form


def device_label(dev: dict) -> str:
    return f"{dev.get('index')}: {dev.get('name', '')}"


def device_spec(label: str) -> str:
    """Label combobox -> spec cho audio_player (index neu co, khong thi giu nguyen ten)."""
    text = str(label).strip()
    if ": " in text:
        head, _ = text.split(": ", 1)
        if head.isdigit():
            return head
    return text


def coerce_value(raw, current):
    """Chuoi tu Entry -> kieu cua gia tri goc. ValueError neu sai dinh dang so."""
    text = str(raw).strip()
    if isinstance(current, bool):
        return text.lower() in ("1", "true", "yes", "on")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(text) if text.lstrip("-").isdigit() else int(float(text))
    if isinstance(current, float):
        return float(text)
    return text


def safe_devices() -> list[dict]:
    """Danh sach thiet bi ra (rong neu thieu sounddevice)."""
    try:
        import audio_player

        return list(audio_player.list_output_devices())
    except Exception:
        return []


# --------------------------------- widget ---------------------------------

class _Field:
    """1 dong config: tao widget theo spec, doc gia tri, ghi gia tri."""

    def __init__(self, app, parent, row: int, spec: dict):
        self.app = app
        self.key = spec["key"]
        self.kind = spec["kind"]
        self.secret = spec["secret"]
        self.original = spec["value"]

        ttk.Label(parent, text=self.key, width=22).grid(row=row, column=0, sticky="w", padx=4, pady=2)

        if self.kind == "bool":
            self.var = tk.BooleanVar(value=bool(self.original))
            self.widget = ttk.Checkbutton(parent, variable=self.var)
        else:
            self.var = tk.StringVar(value="" if self.original is None else str(self.original))
            if self.key == "audio_device":
                self.widget = ttk.Combobox(parent, textvariable=self.var, values=app._device_labels())
            else:
                self.widget = ttk.Entry(
                    parent, textvariable=self.var, width=44, show="*" if self.secret else ""
                )
                if self.kind == "number":
                    is_float = isinstance(self.original, float)
                    self.widget.configure(
                        validate="key",
                        validatecommand=(app.root.register(app.num_ok), "%P", is_float),
                    )
        self.widget.grid(row=row, column=1, sticky="we", padx=4, pady=2)

        if self.secret:
            self.btn = ttk.Button(parent, text="Hiện", width=6, command=self.toggle_secret)
            self.btn.grid(row=row, column=2, padx=4)
        if self.key == "audio_device":
            app.device_widget = self.widget

    def toggle_secret(self) -> None:
        showing = self.widget.cget("show") == ""
        self.widget.configure(show="*" if showing else "")
        self.btn.configure(text="Hiện" if showing else "Ẩn")

    def value(self):
        raw = self.var.get()
        if self.kind == "bool":
            return bool(raw)
        if self.key == "audio_device":
            return device_spec(raw)
        return coerce_value(raw, self.original)

    def set_value(self, value) -> None:
        self.var.set(bool(value) if self.kind == "bool" else str(value))


class App:
    def __init__(self, root, cfg: dict | None = None):
        self.root = root
        self.cfg = dict(cfg if cfg is not None else settings.load())
        self.proc: subprocess.Popen | None = None
        self._proc_start_time: float | None = None
        self.log_q: "queue.Queue[str]" = queue.Queue()
        self._raw_lines: list[str] = []
        self.status_counters = StatusCounters()
        self.devices = safe_devices()
        self.device_widget = None
        self.devices_dirty = False

        root.title(TITLE)
        root.minsize(720, 600)

        # Thanh hanh dong o duoi cung, luon co dinh
        self._build_actions(root)

        # Notebook chiem toan bo phan tren
        self.nb = ttk.Notebook(root)
        self.nb.pack(side="top", fill="both", expand=True, padx=6, pady=(6, 0))

        self.fields: list[_Field] = []
        for sec in build_form(settings.SECTIONS, self.cfg, settings.SECRET_KEYS):
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=sec["section"])
            frame.columnconfigure(1, weight=1)
            for i, spec in enumerate(sec["fields"]):
                self.fields.append(_Field(self, frame, i, spec))

        # Tab Trang thai
        self.tab_status = ttk.Frame(self.nb)
        self.nb.add(self.tab_status, text="Trạng thái")
        self._build_status_tab(self.tab_status)

        # Tab Log dang chay
        self.tab_log = ttk.Frame(self.nb)
        self.nb.add(self.tab_log, text="Log đang chạy")
        self._build_log_tab(self.tab_log)

        self._write(f"config: {settings.config_path()}")
        self._write(f"data  : {launcher.app_dir()} | meipass={getattr(sys, '_MEIPASS', '-')}")
        self._write(f"audio : {len(self.devices)} thiết bị ra")
        self.root.after(POLL_MS, self._poll_log)

    # ------------------------------ tab Trang thai ------------------------------
    def _build_status_tab(self, parent) -> None:
        pad = ttk.Frame(parent, padding=12)
        pad.pack(fill="both", expand=True)

        self.pipeline_status_var = tk.StringVar(value="Đang dừng")
        self.proc_pid_var = tk.StringVar(value="—")
        self.proc_runtime_var = tk.StringVar(value="—")

        self.stat_total_var = tk.StringVar(value="0")
        self.stat_chat_var = tk.StringVar(value="0")
        self.stat_gift_var = tk.StringVar(value="0")
        self.stat_order_var = tk.StringVar(value="0")
        self.stat_join_var = tk.StringVar(value="0")

        self.stat_qsize_var = tk.StringVar(value="0")
        self.stat_played_var = tk.StringVar(value="0")
        self.stat_interrupted_var = tk.StringVar(value="0")
        self.stat_dropped_var = tk.StringVar(value="0")

        # Frame 1: Tien trinh & Pipeline
        lf1 = ttk.LabelFrame(pad, text="Tiến trình & Pipeline", padding=10)
        lf1.pack(fill="x", pady=(0, 10))
        lf1.columnconfigure(1, weight=1)
        lf1.columnconfigure(3, weight=1)

        ttk.Label(lf1, text="Trạng thái:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Label(
            lf1, textvariable=self.pipeline_status_var, font=("", 10, "bold"), foreground="#0066cc"
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(lf1, text="PID tiến trình:").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        ttk.Label(lf1, textvariable=self.proc_pid_var).grid(row=0, column=3, sticky="w", padx=6, pady=4)

        ttk.Label(lf1, text="Thời gian chạy:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(lf1, textvariable=self.proc_runtime_var, font=("", 10, "bold")).grid(
            row=1, column=1, sticky="w", padx=6, pady=4
        )

        # Frame 2: Su kien nhan dien
        lf2 = ttk.LabelFrame(pad, text="Sự kiện nhận diện (từ log)", padding=10)
        lf2.pack(fill="x", pady=(0, 10))
        for c in range(4):
            lf2.columnconfigure(c, weight=1)

        ttk.Label(lf2, text="Tổng sự kiện:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Label(lf2, textvariable=self.stat_total_var, font=("", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

        ttk.Label(lf2, text="Bình luận (chat):").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(lf2, textvariable=self.stat_chat_var).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(lf2, text="Tặng quà (gift):").grid(row=1, column=2, sticky="w", padx=6, pady=4)
        ttk.Label(lf2, textvariable=self.stat_gift_var).grid(row=1, column=3, sticky="w", padx=6, pady=4)

        ttk.Label(lf2, text="Chốt đơn (order):").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(lf2, textvariable=self.stat_order_var).grid(row=2, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(lf2, text="Tham gia (join):").grid(row=2, column=2, sticky="w", padx=6, pady=4)
        ttk.Label(lf2, textvariable=self.stat_join_var).grid(row=2, column=3, sticky="w", padx=6, pady=4)

        # Frame 3: Hang doi & Phat am
        lf3 = ttk.LabelFrame(pad, text="Hàng đợi âm thanh & Phát", padding=10)
        lf3.pack(fill="x", pady=(0, 10))
        for c in range(4):
            lf3.columnconfigure(c, weight=1)

        ttk.Label(lf3, text="Hàng đợi hiện tại:", font=("", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Label(lf3, textvariable=self.stat_qsize_var, font=("", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=6, pady=4
        )

        ttk.Label(lf3, text="Đã phát (played):").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(lf3, textvariable=self.stat_played_var).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(lf3, text="Bị ngắt (interrupted):").grid(row=1, column=2, sticky="w", padx=6, pady=4)
        ttk.Label(lf3, textvariable=self.stat_interrupted_var).grid(row=1, column=3, sticky="w", padx=6, pady=4)

        ttk.Label(lf3, text="Bị bỏ qua (overflow):").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Label(lf3, textvariable=self.stat_dropped_var).grid(row=2, column=1, sticky="w", padx=6, pady=4)

        bar_reset = ttk.Frame(pad)
        bar_reset.pack(fill="x", pady=6)
        ttk.Button(bar_reset, text="Đặt lại số đếm", command=self.reset_status_counters).pack(side="right")

    # ------------------------------ tab Log dang chay ------------------------------
    def _build_log_tab(self, parent) -> None:
        toolbar = ttk.Frame(parent, padding=4)
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="Lọc:").pack(side="left", padx=(2, 4))
        self.log_filter_var = tk.StringVar(value="Tất cả")
        self.filter_cb = ttk.Combobox(
            toolbar,
            textvariable=self.log_filter_var,
            values=["Tất cả", "[app]", "[doctor]", "[check]", "[save]", "[run]", "[gui]"],
            state="readonly",
            width=10,
        )
        self.filter_cb.pack(side="left", padx=2)
        self.filter_cb.bind("<<ComboboxSelected>>", self._on_filter_changed)

        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Tự cuộn", variable=self.autoscroll_var).pack(side="left", padx=6)

        ttk.Button(toolbar, text="Xoá log", command=self.clear_log).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Sao chép log", command=self.copy_log).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Mở thư mục log", command=self.open_log_dir).pack(side="left", padx=3)

        self.log = scrolledtext.ScrolledText(parent, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    def clear_log(self) -> None:
        self._raw_lines.clear()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def copy_log(self) -> None:
        content = self.log.get("1.0", "end-1c")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self._write("[gui] Đã sao chép log vào clipboard")
        except Exception as e:
            self._write(f"[gui] Không sao chép được log: {e}")

    def open_log_dir(self) -> None:
        p = launcher._log_dir()
        p.mkdir(parents=True, exist_ok=True)
        self._open(p)

    def reset_status_counters(self) -> None:
        self.status_counters.reset()
        self._update_status_ui()

    def _line_matches_filter(self, line: str, flt: str) -> bool:
        if not flt or flt == "Tất cả":
            return True
        return line.startswith(flt) or flt in line

    def _on_filter_changed(self, event=None) -> None:
        flt = self.log_filter_var.get()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        to_show = [l for l in self._raw_lines if self._line_matches_filter(l, flt)]
        if to_show:
            self.log.insert("end", "\n".join(to_show) + "\n")
            if self.autoscroll_var.get():
                self.log.see("end")
        self.log.configure(state="disabled")

    def _update_status_ui(self) -> None:
        is_running = self.proc is not None and self.proc.poll() is None
        if is_running:
            st = "Đang chạy mô phỏng" if self.sim_var.get() else "Đang chạy"
            self.pipeline_status_var.set(st)
            self.proc_pid_var.set(str(self.proc.pid))
            if self._proc_start_time is not None:
                elapsed = int(time.monotonic() - self._proc_start_time)
                h, rem = divmod(elapsed, 3600)
                m, s = divmod(rem, 60)
                self.proc_runtime_var.set(f"{h:02d}:{m:02d}:{s:02d}")
        else:
            self.pipeline_status_var.set("Đang dừng")
            self.proc_pid_var.set("—")
            self.proc_runtime_var.set("—")

        snap = self.status_counters.snapshot()
        evs = snap["events"]
        self.stat_total_var.set(str(snap["total_events"]))
        self.stat_chat_var.set(str(evs.get("chat", 0)))
        self.stat_gift_var.set(str(evs.get("gift", 0)))
        self.stat_order_var.set(str(evs.get("order", 0)))
        self.stat_join_var.set(str(evs.get("join", 0)))

        self.stat_qsize_var.set(str(snap["queue_size"]))
        self.stat_played_var.set(str(snap["played"]))
        self.stat_interrupted_var.set(str(snap["interrupted"]))
        self.stat_dropped_var.set(str(snap["dropped"]))

    # ------------------------------ log (thread-safe) ------------------------------
    def _write(self, text: str) -> None:
        """Chi day vao queue: moi thread goi duoc, mainloop khong bi block."""
        self.log_q.put(str(text).rstrip())

    def _poll_log(self) -> None:
        lines = []
        try:
            while True:
                lines.append(self.log_q.get_nowait())
        except queue.Empty:
            pass
        if self.devices_dirty:
            self.devices_dirty = False
            self._fill_devices()

        if lines:
            flt = self.log_filter_var.get()
            to_show = []
            for line in lines:
                self._raw_lines.append(line)
                self.status_counters.feed(line)
                if self._line_matches_filter(line, flt):
                    to_show.append(line)

            if to_show:
                self.log.configure(state="normal")
                self.log.insert("end", "\n".join(to_show) + "\n")
                if self.autoscroll_var.get():
                    self.log.see("end")
                self.log.configure(state="disabled")

        self._update_status_ui()
        self.root.after(POLL_MS, self._poll_log)

    # -------------------------------- actions --------------------------------
    def _build_actions(self, root) -> None:
        bar = ttk.Frame(root)
        bar.pack(side="bottom", fill="x", padx=6, pady=6)
        ttk.Button(bar, text="Lưu", command=self.save).pack(side="left", padx=2)
        ttk.Button(bar, text="Kiểm tra kết nối", command=self.check_connections).pack(side="left", padx=2)
        ttk.Button(bar, text="Khởi động", command=self.start).pack(side="left", padx=2)
        ttk.Button(bar, text="Dừng", command=self.stop).pack(side="left", padx=2)
        ttk.Button(bar, text="Mở file config", command=self.open_config).pack(side="left", padx=2)
        ttk.Button(bar, text="Đọc lại", command=self.reload).pack(side="left", padx=2)
        ttk.Button(bar, text="Chẩn đoán (doctor)", command=self.doctor).pack(side="left", padx=2)
        ttk.Button(bar, text="Mở thư mục log", command=self.open_log_dir).pack(side="left", padx=2)
        self.sim_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Mô phỏng (--sim)", variable=self.sim_var).pack(side="left", padx=8)

    @staticmethod
    def num_ok(proposed: str, is_float: bool) -> bool:
        if proposed in ("", "-", "+", "."):
            return True
        body = proposed.lstrip("-+")
        if body.isdigit():
            return True
        return bool(is_float and body.count(".") <= 1 and body.replace(".", "").isdigit())

    def _open(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # chi Windows; GUI nay build cho Windows
        except Exception as e:
            self._write(f"khong mo duoc {path}: {e}")

    def _device_labels(self) -> list[str]:
        return [device_label(d) for d in self.devices]

    def _fill_devices(self) -> None:
        if self.device_widget is not None:
            self.device_widget.configure(values=self._device_labels())

    def collect(self) -> dict:
        """Doc form -> cfg. ValueError neu co o so sai dinh dang."""
        cfg = dict(self.cfg)
        errors = []
        for f in self.fields:
            try:
                cfg[f.key] = f.value()
            except ValueError:
                errors.append(f"{f.key}={f.var.get()!r} không phải số hợp lệ")
        if errors:
            raise ValueError("; ".join(errors))
        return cfg

    def save(self) -> None:
        try:
            cfg = self.collect()
            path = settings.save(cfg)
            settings.apply(cfg)
            self.cfg = cfg
        except Exception as e:
            self._write(f"[save] lỗi: {type(e).__name__}: {e}")
            return
        self._write(f"[save] đã lưu + áp dụng: {path}")

    def reload(self) -> None:
        self.cfg = settings.load()
        for f in self.fields:
            if f.key in self.cfg:
                f.set_value(self.cfg[f.key])
        self._fill_devices()
        self._write("đã đọc lại config từ đĩa")

    def open_config(self) -> None:
        path = settings.config_path()
        self._write(f"[config] {path}")
        self._open(path)

    # ---------------------------- kiem tra ket noi ----------------------------
    def check_connections(self) -> None:
        try:
            cfg = self.collect()
        except ValueError as e:
            self._write(f"[check] lỗi form: {e}")
            return
        settings.save(cfg)
        self.cfg = cfg
        threading.Thread(target=self._check_worker, args=(cfg,), daemon=True, name="gui-check").start()

    def _check_worker(self, cfg: dict) -> None:
        self._write("[check] bắt đầu…")
        settings.apply(cfg)
        sys.modules.pop("llm_client", None)

        try:
            import tts_client

            h = tts_client.health()
            self._write(
                f"[check] TTS {'OK  ' if h['ok'] else 'FAIL'} {h['url']} "
                f"version={h['version']} voices={h['voices']} err={h['error']}"
            )
        except Exception as e:
            self._write(f"[check] TTS lỗi: {type(e).__name__}: {e}")

        try:
            import llm_client

            ans = llm_client.chat("Bạn là trợ lý.", "Trả lời đúng một từ: OK", timeout=10.0)
            self._write(f"[check] LLM OK: {ans.strip()[:80]!r}")
        except Exception as e:
            self._write(f"[check] LLM lỗi: {type(e).__name__}: {e}")

        try:
            import audio_player

            devs = list(audio_player.list_output_devices())
            self.devices = devs
            self.devices_dirty = True
            self._write(
                f"[check] Audio: {len(devs)} thiết bị ra; đang dùng {audio_player.output_device_name()}"
            )
        except Exception as e:
            self._write(f"[check] Audio lỗi: {type(e).__name__}: {e}")
        self._write("[check] xong")

    # ------------------------------ start / stop ------------------------------
    def _command(self) -> list[str]:
        cmd = child_cmd(["run"])
        if self.sim_var.get():
            cmd.append("--sim")
        return cmd

    def start(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self._write("[run] tiến trình đang chạy, bấm Dừng trước")
            return
        try:
            cfg = self.collect()
            path = settings.save(cfg)
            settings.apply(cfg)
            self.cfg = cfg
        except Exception as e:
            self._write(f"[run] không khởi động được: {type(e).__name__}: {e}")
            return
        self._write(f"[save] đã lưu + áp dụng: {path}")

        cmd = self._command()
        self._write(f"[run] {subprocess.list2cmdline(cmd)}")
        self.proc = self._spawn(cmd, tag="[app]")

    def stop(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            self._write("[run] không có tiến trình nào đang chạy")
            return
        self._write("[run] đang dừng…")

        def work() -> None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            self._proc_start_time = None

        threading.Thread(target=work, daemon=True, name="gui-stop").start()

    def _spawn(self, cmd: list[str], tag: str = "[app]") -> subprocess.Popen | None:
        """Mo tien trinh con + thread doc stdout vao log. Tra None neu mo loi."""
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(launcher.app_dir()),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
        except Exception as e:
            self._write(f"{tag} lỗi mở tiến trình: {type(e).__name__}: {e}")
            return None
        self._proc_start_time = time.monotonic()
        threading.Thread(target=self._pump, args=(proc, tag), daemon=True, name="gui-pump").start()
        return proc

    def _pump(self, proc: subprocess.Popen, tag: str = "[app]") -> None:
        """Doc stdout cua tien trinh con -> log (khong block mainloop)."""
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._write(f"{tag} {line.rstrip()}")
        except Exception as e:
            self._write(f"{tag} lỗi đọc log: {type(e).__name__}: {e}")
        self._write(f"{tag} tiến trình kết thúc (exit={proc.wait()})")
        self._proc_start_time = None

    # -------------------------------- doctor --------------------------------
    def doctor(self) -> None:
        """Chay `app.py doctor` trong tien trinh rieng, doc ket qua vao log."""
        self._write("--- doctor ---")
        self._spawn(child_cmd(["doctor"]), tag="[doctor]")


def main() -> int:
    if TK_ERROR is not None:
        print(f"[gui] tkinter không khả dụng: {TK_ERROR}", file=sys.stderr)
        print("[gui] dùng CLI thay thế: python src/app.py doctor", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except Exception as e:  # headless / khong co display
        print(f"[gui] không mở được cửa sổ: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    App(root, settings.load())
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
