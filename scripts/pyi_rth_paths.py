"""Runtime hook: chay TRUOC khi app import. Chuan hoa sys.path khi frozen.

Van de: `src/` duoc PyInstaller gom vao _internal/ duoi dang module phang (app.py,
gui.py, settings.py...), nhung llm_client.py import `src.config` va app.py chen goc
repo vao sys.path. Khi frozen khong co goc repo -> cac import do se fail.

Hook nay:
  1. Them thu muc _internal (sys._MEIPASS) vao sys.path.
  2. Tao alias package `src` tro ve module phang, de `from src.config import ...`,
     `import src.config as c` hoat dong nhat quan du chay source hay frozen.
"""
import sys
import types


def _install_src_alias() -> None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return
    if meipass not in sys.path:
        sys.path.insert(0, meipass)

    if "src" in sys.modules:
        return

    pkg = types.ModuleType("src")
    pkg.__path__ = [meipass]  # type: ignore[attr-defined]
    pkg.__package__ = "src"
    sys.modules["src"] = pkg

    class _Finder:
        """Meta path finder: `src.X` -> module phang `X` trong _internal."""

        def find_module(self, fullname, path=None):  # legacy API, du cho py3.11
            if fullname.startswith("src."):
                return self
            return None

        def load_module(self, fullname):
            import importlib

            name = fullname.split(".", 1)[1]
            if fullname in sys.modules:
                return sys.modules[fullname]
            mod = importlib.import_module(name)
            sys.modules[fullname] = mod
            return mod

    sys.meta_path.append(_Finder())


_install_src_alias()
