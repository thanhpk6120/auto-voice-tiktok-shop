"""GUI (tkinter) - cau hinh ket noi + Start/Stop + log realtime.

Mo bang: chay .exe khong tham so, hoac `python src/launcher.py` (khong tham so),
hoac truc tiep `python src/gui.py`.

Toan bo schema lay tu `settings.SECTIONS` / `DEFAULTS` / `SECRET_KEYS` nen them key
moi chi can sua settings.py. Logic thuan (build_form/coerce_value/device_spec) tach
rieng de test khong can mainloop.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
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
    for section, keys in sections.items():
        fields = []
        for key in keys:
            value = cfg.get(key, "")
            fields.append(
                {
                    "key": key,
                    "value": value,
                    "kind": field_kind(value),
                    "secret": key in secrets,
                }
            )
        form.append({"section": section, "fields": fields})
    return form


def device_label(dev: dict) -> str:
    return f"{dev.get('index')}: {dev.get('name', '')}"


def device_spec(label: str) -> str:
    """Label combobox -> spec cho audio_player (index neu co, khong thi giu nguyen ten)."""
    text = str(label).strip()
    head, sep, _ = text.partition(":")
    if sep and head.strip().lstrip("-").isdigit():
        return head.strip()
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
        self.log_q: "queue.Queue[str]" = queue.Queue()
        self.devices = safe_devices()
        self.device_widget = None
        self.devices_dirty = False

        root.title(TITLE)
        root.minsize(680, 560)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        self.fields: list[_Field] = []
        for sec in build_form(settings.SECTIONS, self.cfg, settings.SECRET_KEYS):
            frame = ttk.Frame(nb)
            nb.add(frame, text=sec["section"])
            frame.columnconfigure(1, weight=1)
            for i, spec in enumerate(sec["fields"]):
                self.fields.append(_Field(self, frame, i, spec))

        self._build_actions(root)

        self.log = scrolledtext.ScrolledText(root, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._write(f"config: {settings.config_path()}")
        self._write(f"data  : {launcher.app_dir()} | meipass={getattr(sys, '_MEIPASS', '-')}")
        self._write(f"audio : {len(self.devices)} thiết bị ra")
        self.root.after(POLL_MS, self._poll_log)

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
            self.log.configure(state="normal")
            self.log.insert("end", "\n".join(lines) + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(POLL_MS, self._poll_log)

    # -------------------------------- actions --------------------------------
    def _build_actions(self, root) -> None:
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=6)
        ttk.Button(bar, text="Lưu", command=self.save).pack(side="left", padx=2)
        ttk.Button(bar, text="Kiểm tra kết nối", command=self.check_connections).pack(side="left", padx=2)
        ttk.Button(bar, text="Khởi động", command=self.start).pack(side="left", padx=2)
        ttk.Button(bar, text="Dừng", command=self.stop).pack(side="left", padx=2)
        ttk.Button(bar, text="Mở file config", command=self.open_config).pack(side="left", padx=2)
        ttk.Button(bar, text="Đọc lại", command=self.reload).pack(side="left", padx=2)
        ttk.Button(bar, text="Chẩn đoán (doctor)", command=self.doctor).pack(side="left", padx=2)
        ttk.Button(bar, text="Mở thư mục log", command=lambda: self._open(launcher._log_dir())).pack(
            side="left", padx=2
        )
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
        # llm_client bind hang so luc import -> xoa de lan import sau lay cfg vua apply
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
            self.devices_dirty = True  # tkinter khong thread-safe -> de _poll_log cap nhat
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
