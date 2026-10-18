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
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    TK_ERROR: str | None = None
except Exception as _e:  # pragma: no cover - may thieu tkinter / headless
    tk = None  # type: ignore
    ttk = None  # type: ignore
    scrolledtext = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore
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

def extract_profile_id(raw: str) -> str:
    """Tách profile id từ chuỗi dropdown: 'Name (id)' -> 'id'."""
    s = str(raw).strip()
    if s.endswith(")") and " (" in s:
        return s.rsplit(" (", 1)[1][:-1].strip()
    return s


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

        ttk.Label(parent, text=self.key, width=24).grid(row=row, column=0, sticky="w", padx=6, pady=4)

        if self.kind == "bool":
            self.var = tk.BooleanVar(value=bool(self.original))
            self.widget = ttk.Checkbutton(parent, variable=self.var)
        else:
            self.var = tk.StringVar(value="" if self.original is None else str(self.original))
            if self.key == "audio_device":
                self.widget = ttk.Combobox(parent, textvariable=self.var, values=app._device_labels(), width=46)
            elif self.key == "browser_mode":
                self.widget = ttk.Combobox(
                    parent,
                    textvariable=self.var,
                    values=["gologin_cdp", "extension"],
                    state="readonly",
                    width=46,
                )
            elif self.key == "gologin_profile_id":
                self.widget = ttk.Combobox(
                    parent,
                    textvariable=self.var,
                    values=app._gologin_profile_ids(),
                    width=46,
                )
                app.profile_widget = self.widget
            elif self.key == "gologin_active_version":
                self.widget = ttk.Combobox(
                    parent,
                    textvariable=self.var,
                    values=app._chrome_version_labels(),
                    width=46,
                )
                app.chrome_version_widget = self.widget
            else:
                self.widget = ttk.Entry(
                    parent, textvariable=self.var, width=48, show="*" if self.secret else ""
                )
                if self.kind == "number":
                    is_float = isinstance(self.original, float)
                    self.widget.configure(
                        validate="key",
                        validatecommand=(app.root.register(app.num_ok), "%P", is_float),
                    )
        self.widget.grid(row=row, column=1, sticky="we", padx=6, pady=4)

        if self.secret:
            self.btn = ttk.Button(parent, text="Hiện", width=6, command=self.toggle_secret)
            self.btn.grid(row=row, column=2, padx=4)
        elif self.key in ("gologin_dir", "gologin_profiles_dir", "prompts_dir", "context_dir", "out_dir"):
            btn = ttk.Button(
                parent,
                text="Chọn thư mục...",
                command=lambda k=self.key, v=self.var: app._choose_directory(k, v),
            )
            btn.grid(row=row, column=2, padx=4)
        elif self.key == "gologin_profile_id":
            btn_add = ttk.Button(parent, text="➕ Tạo Mới...", command=app._open_create_profile_dialog)
            btn_add.grid(row=row, column=2, padx=2)
            btn_refresh = ttk.Button(parent, text="🔄 Làm mới", command=app._refresh_profiles)
            btn_refresh.grid(row=row, column=3, padx=2)
            btn_launch = ttk.Button(parent, text="🚀 Mở Profile", command=app._launch_profile)
            btn_launch.grid(row=row, column=4, padx=2)
        elif self.key == "gologin_active_version":
            btn_act = ttk.Button(parent, text="Kích hoạt", command=app._activate_selected_version)
            btn_act.grid(row=row, column=2, padx=2)
            btn_mgr = ttk.Button(parent, text="Quản lý Chrome...", command=app._open_chrome_manager_dialog)
            btn_mgr.grid(row=row, column=3, padx=2)
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
        if self.key == "gologin_profile_id":
            return extract_profile_id(raw)
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
        root.minsize(920, 680)
        self._center_window(1040, 780)
        self._setup_styles()

        self.device_widget = None
        self.profile_widget = None
        self.chrome_version_widget = None

        # 1. Thanh hanh dong o duoi cung nhat
        self._build_actions(root)

        # 2. Khung log hoat dong luon hien thi o duoi cung (Khong nam trong tab)
        self.log_frame = ttk.LabelFrame(root, text="Log hoạt động (Thời gian thực)", padding=6)
        self.log_frame.pack(side="bottom", fill="x", padx=8, pady=(0, 6))
        self._build_log_panel(self.log_frame)
        self.tab_log = self.log_frame

        # 3. Notebook o phan tren
        self.nb = ttk.Notebook(root)
        self.nb.pack(side="top", fill="both", expand=True, padx=8, pady=6)

        self.fields: list[_Field] = []
        for sec in build_form(settings.SECTIONS, self.cfg, settings.SECRET_KEYS):
            frame = ttk.Frame(self.nb, padding=6)
            self.nb.add(frame, text=sec["section"])
            frame.columnconfigure(1, weight=1)
            for i, spec in enumerate(sec["fields"]):
                self.fields.append(_Field(self, frame, i, spec))

        # Tab Trang thai
        self.tab_status = ttk.Frame(self.nb, padding=6)
        self.nb.add(self.tab_status, text="Trạng thái")
        self._build_status_tab(self.tab_status)
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

    # ------------------------------ Khung log hoat dong (luon hien thi o duoi) ------------------------------
    def _build_log_panel(self, parent) -> None:
        toolbar = ttk.Frame(parent, padding=(2, 2))
        toolbar.pack(fill="x", pady=(0, 2))

        ttk.Label(toolbar, text="Lọc:").pack(side="left", padx=(2, 4))
        self.log_filter_var = tk.StringVar(value="Tất cả")
        filters = ["Tất cả", "[app]", "[cdp]", "[doctor]", "[check]", "[save]", "[run]", "[gui]", "[browser]"]
        self.filter_cb = ttk.Combobox(toolbar, textvariable=self.log_filter_var, values=filters, state="readonly", width=12)
        self.filter_cb.pack(side="left", padx=2)
        self.filter_cb.bind("<<ComboboxSelected>>", self._on_filter_changed)

        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Tự cuộn", variable=self.autoscroll_var).pack(side="left", padx=6)

        ttk.Button(toolbar, text="Xoá log", command=self.clear_log).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Sao chép log", command=self.copy_log).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Mở thư mục log", command=self.open_log_dir).pack(side="left", padx=3)

        self.log = scrolledtext.ScrolledText(parent, height=10, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=2, pady=(2, 2))

    _build_log_tab = _build_log_panel
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
    def _center_window(self, width: int, height: int) -> None:
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 2)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self.root.geometry(f"{width}x{height}")

    def _setup_styles(self) -> None:
        try:
            style = ttk.Style()
            if "clam" in style.theme_names():
                style.theme_use("clam")
            style.configure("TButton", padding=(8, 4), font=("Segoe UI", 9))
            style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), foreground="#0055aa")
            style.configure("Danger.TButton", font=("Segoe UI", 9, "bold"), foreground="#bb2200")
            style.configure("TLabel", font=("Segoe UI", 9))
            style.configure("TCheckbutton", font=("Segoe UI", 9))
            style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"))
        except Exception:
            pass

    def _build_actions(self, root) -> None:
        bar = ttk.Frame(root, padding=(8, 6))
        bar.pack(side="bottom", fill="x")

        ttk.Button(bar, text="▶ Khởi động", command=self.start, style="Primary.TButton").pack(side="left", padx=3)
        ttk.Button(bar, text="⏹ Dừng", command=self.stop, style="Danger.TButton").pack(side="left", padx=3)

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)

        ttk.Button(bar, text="💾 Lưu cấu hình", command=self.save).pack(side="left", padx=3)
        ttk.Button(bar, text="🔌 Kiểm tra kết nối", command=self.check_connections).pack(side="left", padx=3)
        ttk.Button(bar, text="🩺 Chẩn đoán (doctor)", command=self.doctor).pack(side="left", padx=3)
        ttk.Button(bar, text="🔄 Đọc lại", command=self.reload).pack(side="left", padx=3)
        ttk.Button(bar, text="📂 Mở file config", command=self.open_config).pack(side="left", padx=3)

        self.sim_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Mô phỏng (--sim)", variable=self.sim_var).pack(side="right", padx=6)

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

    # ---------------------------- Browser & GoLogin ----------------------------
    def _get_field_val(self, key: str) -> str:
        for f in self.fields:
            if f.key == key:
                return str(f.var.get()).strip()
        return str(self.cfg.get(key) or "").strip()

    def _choose_directory(self, key: str, var: tk.StringVar) -> None:
        init_dir = var.get().strip() or os.getcwd()
        if filedialog:
            folder = filedialog.askdirectory(parent=self.root, title=f"Chọn thư mục cho {key}", initialdir=init_dir)
            if folder:
                var.set(folder)
                self._write(f"[browser] Đã chọn {key}: {folder}")
                if key == "gologin_dir":
                    self._refresh_chrome_versions()
                if key in ("gologin_dir", "gologin_profiles_dir"):
                    self._refresh_profiles()

    def _gologin_profile_ids(self) -> list[str]:
        try:
            import browser_manager
            p_dir = self._get_field_val("gologin_profiles_dir")
            g_dir = self._get_field_val("gologin_dir")
            resolved_p = browser_manager.resolve_profiles_dir(p_dir or None, g_dir or None)
            profiles = browser_manager.list_gologin_profiles(resolved_p)
            res = []
            for p in profiles:
                if p["name"] and p["name"] != p["id"]:
                    res.append(f"{p['name']} ({p['id']})")
                else:
                    res.append(p["id"])
            return res
        except Exception:
            return []

    def _chrome_version_labels(self) -> list[str]:
        try:
            import browser_manager
            g_dir = self._get_field_val("gologin_dir")
            resolved_g = browser_manager.resolve_gologin_dir(g_dir or None)
            return browser_manager.get_installed_chrome_versions(resolved_g)
        except Exception:
            return []

    def _refresh_profiles(self) -> None:
        ids = self._gologin_profile_ids()
        if self.profile_widget is not None:
            self.profile_widget.configure(values=ids)
            if ids and not self.profile_widget.get():
                self.profile_widget.set(ids[0])
        self._write(f"[browser] Đã làm mới danh sách profiles ({len(ids)} profile)")

    def _refresh_chrome_versions(self) -> None:
        vers = self._chrome_version_labels()
        if self.chrome_version_widget is not None:
            self.chrome_version_widget.configure(values=vers)
            try:
                import browser_manager
                g_dir = self._get_field_val("gologin_dir")
                active = browser_manager.get_active_chrome_version(g_dir or None)
                if active and (not self.chrome_version_widget.get() or self.chrome_version_widget.get() not in vers):
                    self.chrome_version_widget.set(active)
            except Exception:
                pass
        self._write(f"[browser] Đã làm mới phiên bản Chrome đã cài ({len(vers)} bản)")

    def _activate_selected_version(self) -> None:
        ver = self.chrome_version_widget.get().strip() if self.chrome_version_widget else ""
        if not ver:
            self._write("[browser] Chưa chọn phiên bản Chrome để kích hoạt")
            return
        try:
            import browser_manager
            g_dir = self._get_field_val("gologin_dir")
            ok, msg = browser_manager.set_active_chrome_version(g_dir or None, ver)
            self._write(f"[browser] {msg}")
            if ok and messagebox:
                messagebox.showinfo("Kích hoạt Chrome", msg, parent=self.root)
            elif not ok and messagebox:
                messagebox.showerror("Lỗi", msg, parent=self.root)
        except Exception as e:
            self._write(f"[browser] Lỗi kích hoạt Chrome: {e}")

    def _launch_profile(self) -> None:
        raw = self.profile_widget.get().strip() if self.profile_widget else ""
        pid = extract_profile_id(raw)
        if not pid:
            self._write("[browser] Chưa có profile nào được chọn hoặc tạo. Mở hộp thoại tạo profile mới.")
            if messagebox:
                if messagebox.askyesno(
                    "Chưa có Profile",
                    "Hiện chưa chọn Profile nào. Bạn có muốn tạo Profile GoLogin mới ngay bây giờ không?",
                    parent=self.root,
                ):
                    self._open_create_profile_dialog()
            return
        try:
            import browser_manager
            g_dir = self._get_field_val("gologin_dir")
            p_dir = self._get_field_val("gologin_profiles_dir")
            proc, port, url = browser_manager.launch_gologin_profile(
                profile_id=pid,
                gologin_dir=g_dir or None,
                profiles_dir=p_dir or None,
            )
            if proc is None:
                self._write(f"[browser] Không mở được profile: {url}")
                if messagebox:
                    messagebox.showerror("Lỗi khởi chạy", url, parent=self.root)
            else:
                self._write(f"[browser] Đã mở profile '{pid}' (PID={proc.pid}, CDP debug: {url})")
        except Exception as e:
            self._write(f"[browser] Lỗi mở profile: {e}")
    def _open_create_profile_dialog(self) -> None:
        if not tk:
            return
        try:
            import browser_manager
        except Exception as e:
            self._write(f"[browser] Lỗi import browser_manager: {e}")
            return

        g_dir = self._get_field_val("gologin_dir")
        p_dir = self._get_field_val("gologin_profiles_dir")
        resolved_g = browser_manager.resolve_gologin_dir(g_dir or None)
        resolved_p = browser_manager.resolve_profiles_dir(p_dir or None, resolved_g)
        installed_vers = browser_manager.get_installed_chrome_versions(resolved_g)
        active_ver = browser_manager.get_active_chrome_version(resolved_g)

        win = tk.Toplevel(self.root)
        win.title("Tạo Profile GoLogin Mới")
        win.minsize(540, 520)
        win.transient(self.root)
        win.grab_set()

        try:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            win.geometry(f"560x540+{(sw-560)//2}+{(sh-540)//2}")
        except Exception:
            pass

        pad = ttk.Frame(win, padding=16)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="Cấu hình thông số Profile mới", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))

        grid_frame = ttk.Frame(pad)
        grid_frame.pack(fill="both", expand=True)
        grid_frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(grid_frame, text="Tên Profile:").grid(row=row, column=0, sticky="w", pady=4)
        name_var = tk.StringVar(value="TikTok Shop Live")
        ttk.Entry(grid_frame, textvariable=name_var).grid(row=row, column=1, sticky="we", padx=6, pady=4)

        row += 1
        ttk.Label(grid_frame, text="Phiên bản Chrome:").grid(row=row, column=0, sticky="w", pady=4)
        ver_var = tk.StringVar(value=active_ver if active_ver else (installed_vers[0] if installed_vers else "141"))
        cb_ver = ttk.Combobox(grid_frame, textvariable=ver_var, values=installed_vers or ["141", "120"], state="readonly")
        cb_ver.grid(row=row, column=1, sticky="we", padx=6, pady=4)

        row += 1
        ttk.Label(grid_frame, text="Độ phân giải:").grid(row=row, column=0, sticky="w", pady=4)
        res_var = tk.StringVar(value="1920x1080")
        cb_res = ttk.Combobox(grid_frame, textvariable=res_var, values=["1920x1080", "1366x768", "1440x900", "2560x1440", "1280x720"], state="readonly")
        cb_res.grid(row=row, column=1, sticky="we", padx=6, pady=4)

        row += 1
        ttk.Label(grid_frame, text="Ngôn ngữ:").grid(row=row, column=0, sticky="w", pady=4)
        lang_var = tk.StringVar(value="vi-VN")
        cb_lang = ttk.Combobox(grid_frame, textvariable=lang_var, values=["vi-VN", "en-US"], state="readonly")
        cb_lang.grid(row=row, column=1, sticky="we", padx=6, pady=4)

        row += 1
        ttk.Label(grid_frame, text="URL khởi động:").grid(row=row, column=0, sticky="w", pady=4)
        url_var = tk.StringVar(value="https://shop.tiktok.com/streamer/live/product/dashboard")
        ttk.Entry(grid_frame, textvariable=url_var).grid(row=row, column=1, sticky="we", padx=6, pady=4)

        row += 1
        grp_proxy = ttk.LabelFrame(grid_frame, text="Cấu hình Proxy (Tuỳ chọn)", padding=8)
        grp_proxy.grid(row=row, column=0, columnspan=2, sticky="we", pady=(10, 4))
        grp_proxy.columnconfigure(1, weight=1)

        p_row = 0
        ttk.Label(grp_proxy, text="Loại Proxy:").grid(row=p_row, column=0, sticky="w", pady=2)
        proxy_mode_var = tk.StringVar(value="none")
        cb_pm = ttk.Combobox(grp_proxy, textvariable=proxy_mode_var, values=["none", "http", "socks5"], state="readonly", width=12)
        cb_pm.grid(row=p_row, column=1, sticky="w", padx=6, pady=2)

        p_row += 1
        ttk.Label(grp_proxy, text="Host / IP:").grid(row=p_row, column=0, sticky="w", pady=2)
        host_var = tk.StringVar()
        ttk.Entry(grp_proxy, textvariable=host_var).grid(row=p_row, column=1, sticky="we", padx=6, pady=2)

        p_row += 1
        ttk.Label(grp_proxy, text="Cổng (Port):").grid(row=p_row, column=0, sticky="w", pady=2)
        port_var = tk.StringVar()
        ttk.Entry(grp_proxy, textvariable=port_var, width=12).grid(row=p_row, column=1, sticky="w", padx=6, pady=2)

        p_row += 1
        ttk.Label(grp_proxy, text="Username:").grid(row=p_row, column=0, sticky="w", pady=2)
        user_var = tk.StringVar()
        ttk.Entry(grp_proxy, textvariable=user_var).grid(row=p_row, column=1, sticky="we", padx=6, pady=2)

        p_row += 1
        ttk.Label(grp_proxy, text="Mật khẩu:").grid(row=p_row, column=0, sticky="w", pady=2)
        pass_var = tk.StringVar()
        ttk.Entry(grp_proxy, textvariable=pass_var, show="*").grid(row=p_row, column=1, sticky="we", padx=6, pady=2)

        btn_box = ttk.Frame(pad)
        btn_box.pack(fill="x", pady=(14, 0))

        def _create():
            p_name = name_var.get().strip() or "TikTok Shop Live"
            p_ver = ver_var.get().strip()
            p_res = res_var.get().strip()
            p_lang = lang_var.get().strip()
            p_url = url_var.get().strip()
            pm = proxy_mode_var.get().strip()
            ph = host_var.get().strip()
            pp = port_var.get().strip()
            pu = user_var.get().strip()
            pw = pass_var.get().strip()

            profile, msg = browser_manager.create_gologin_profile(
                profiles_dir=resolved_p,
                gologin_dir=resolved_g,
                name=p_name,
                version=p_ver,
                resolution=p_res,
                language=p_lang,
                proxy_mode=pm,
                proxy_host=ph,
                proxy_port=int(pp) if pp.isdigit() else 0,
                proxy_user=pu,
                proxy_pass=pw,
                start_url=p_url,
            )
            if profile:
                self._write(f"[browser] {msg}")
                self._refresh_profiles()
                new_label = f"{profile['name']} ({profile['id']})"
                if self.profile_widget:
                    self.profile_widget.set(new_label)
                for f in self.fields:
                    if f.key == "gologin_profile_id":
                        f.var.set(new_label)
                if messagebox:
                    messagebox.showinfo("Thành công", f"Đã tạo profile thành công!\n\nID: {profile['id']}", parent=win)
                win.destroy()
            else:
                self._write(f"[browser] Lỗi tạo profile: {msg}")
                if messagebox:
                    messagebox.showerror("Lỗi", msg, parent=win)

        ttk.Button(btn_box, text="Tạo Profile", command=_create, style="Primary.TButton").pack(side="right", padx=6)
        ttk.Button(btn_box, text="Huỷ", command=win.destroy).pack(side="right", padx=4)

    def _open_chrome_manager_dialog(self) -> None:
        try:
            import browser_manager
        except Exception as e:
            self._write(f"[browser] Lỗi import browser_manager: {e}")
            return

        g_dir = self._get_field_val("gologin_dir")
        resolved_g_dir = browser_manager.resolve_gologin_dir(g_dir or None)

        if not tk:
            return

        win = tk.Toplevel(self.root)
        win.title("Quản lý phiên bản Chrome & Orbita")
        win.minsize(580, 430)
        win.transient(self.root)
        win.grab_set()

        pad = ttk.Frame(win, padding=12)
        pad.pack(fill="both", expand=True)

        lbl_info = ttk.Label(pad, text=f"Thư mục Orbita: {resolved_g_dir}", font=("", 9))
        lbl_info.pack(anchor="w", pady=(0, 6))

        grp_installed = ttk.LabelFrame(pad, text="Các phiên bản đã cài đặt", padding=8)
        grp_installed.pack(fill="both", expand=True, pady=(0, 10))

        frame_list = ttk.Frame(grp_installed)
        frame_list.pack(fill="both", expand=True)

        lb = tk.Listbox(frame_list, height=6)
        lb.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame_list, orient="vertical", command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.configure(yscrollcommand=sb.set)

        def _refresh_list():
            lb.delete(0, "end")
            active_ver = browser_manager.get_active_chrome_version(resolved_g_dir)
            versions = browser_manager.get_installed_chrome_versions(resolved_g_dir)
            for v in versions:
                tag = " [ĐANG KÍCH HOẠT]" if v == active_ver else ""
                lb.insert("end", f"{v}{tag}")

        _refresh_list()

        btn_row = ttk.Frame(grp_installed)
        btn_row.pack(fill="x", pady=(6, 0))

        def _act():
            sel = lb.curselection()
            if not sel:
                if messagebox:
                    messagebox.showwarning("Cảnh báo", "Vui lòng chọn 1 phiên bản từ danh sách.", parent=win)
                return
            item_text = lb.get(sel[0]).split()[0]
            ok, msg = browser_manager.set_active_chrome_version(resolved_g_dir, item_text)
            self._write(f"[browser] {msg}")
            if ok:
                _refresh_list()
                self._refresh_chrome_versions()
                if messagebox:
                    messagebox.showinfo("Thành công", msg, parent=win)
            else:
                if messagebox:
                    messagebox.showerror("Lỗi", msg, parent=win)

        def _del():
            sel = lb.curselection()
            if not sel:
                if messagebox:
                    messagebox.showwarning("Cảnh báo", "Vui lòng chọn 1 phiên bản từ danh sách để xoá.", parent=win)
                return
            item_text = lb.get(sel[0]).split()[0]
            if messagebox and not messagebox.askyesno("Xác nhận xoá", f"Bạn có chắc muốn xoá phiên bản Chrome {item_text}?", parent=win):
                return
            ok, msg = browser_manager.delete_chrome_version(resolved_g_dir, item_text)
            self._write(f"[browser] {msg}")
            if ok:
                _refresh_list()
                self._refresh_chrome_versions()
                if messagebox:
                    messagebox.showinfo("Thành công", msg, parent=win)
            else:
                if messagebox:
                    messagebox.showerror("Lỗi", msg, parent=win)

        ttk.Button(btn_row, text="Kích hoạt phiên bản này", command=_act).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Xoá phiên bản này", command=_del).pack(side="left", padx=4)

        grp_dl = ttk.LabelFrame(pad, text="Tải phiên bản mới từ GitHub Release", padding=8)
        grp_dl.pack(fill="x", expand=False)

        row_dl = ttk.Frame(grp_dl)
        row_dl.pack(fill="x", pady=4)

        ttk.Label(row_dl, text="Chọn phiên bản:").pack(side="left", padx=(0, 6))
        remote_releases = browser_manager.fetch_remote_chrome_releases()
        ver_map = {(r.get("name") or r["version"]): r for r in remote_releases}
        ver_options = list(ver_map.keys())

        dl_var = tk.StringVar(value=ver_options[0] if ver_options else "")
        cb_dl = ttk.Combobox(row_dl, textvariable=dl_var, values=ver_options, state="readonly", width=42)
        cb_dl.pack(side="left", padx=4)

        lbl_dl_status = ttk.Label(grp_dl, text="Sẵn sàng tải.", foreground="gray")
        lbl_dl_status.pack(anchor="w", pady=(4, 0))

        def _start_download():
            chosen_label = dl_var.get()
            if not chosen_label or chosen_label not in ver_map:
                if messagebox:
                    messagebox.showwarning("Cảnh báo", "Vui lòng chọn phiên bản hợp lệ.", parent=win)
                return
            info = ver_map[chosen_label]
            chosen_ver = info["version"]
            lbl_dl_status.configure(text=f"Đang tải {chosen_label}... Vui lòng đợi trong giây lát.", foreground="blue")
            self._write(f"[browser] Bắt đầu tải {chosen_label}...")

            def _worker():
                def _prog(msg):
                    self._write(f"[browser] {msg}")
                    def _ui_msg():
                        try:
                            if win.winfo_exists():
                                lbl_dl_status.configure(text=msg)
                        except Exception:
                            pass
                    self.root.after(0, _ui_msg)

                ok, msg = browser_manager.install_chrome_from_url(
                    resolved_g_dir,
                    chosen_ver,
                    chrome_url=info["chrome_url"],
                    driver_url=info.get("driver_url"),
                    progress_cb=_prog,
                )
                self._write(f"[browser] {msg}")
                def _ui_done():
                    try:
                        if win.winfo_exists():
                            if ok:
                                lbl_dl_status.configure(text=f"✅ {msg}", foreground="green")
                                _refresh_list()
                                self._refresh_chrome_versions()
                            else:
                                lbl_dl_status.configure(text=f"❌ {msg}", foreground="red")
                    except Exception:
                        pass
                self.root.after(0, _ui_done)
            threading.Thread(target=_worker, daemon=True).start()

        ttk.Button(row_dl, text="Tải và Cài đặt", command=_start_download).pack(side="left", padx=6)

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
