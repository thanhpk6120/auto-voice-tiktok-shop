"""Chuẩn hoá & trích xuất JSON từ phản hồi LLM.

LLM (đặc biệt model nhỏ) hay trả về JSON lỗi. Module này gom mọi mẹo làm sạch
vào một chỗ để mọi prompt "only JSON" đều lấy được kết quả chính xác.

Thứ tự thử khi parse:
  1. json.loads trực tiếp
  2. Bỏ code fence ```json ... ```, lời dẫn trước/sau
  3. Cắt đúng khối {...} hoặc [...] cân bằng ngoặc (tôn trọng chuỗi/escape)
  4. Sửa lỗi phổ biến: dấu phẩy thừa, nháy đơn, nháy cong, key không nháy,
     True/False/None/NaN, comment JS, xuống dòng trong chuỗi
  5. ast.literal_eval (JSON kiểu Python)
"""
from __future__ import annotations

import ast
import json
import re

__all__ = [
    "strip_code_fence",
    "extract_json_block",
    "repair_json",
    "parse_json_loose",
    "as_list",
    "as_dict",
    "get_str",
    "get_int",
    "get_bool",
]

_FENCE_RE = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n?(.*?)```", re.DOTALL)
_SMART_MAP = {
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\uff02": '"', "\uff07": "'",
    "\u00a0": " ",
}


def strip_code_fence(text: str) -> str:
    """Bỏ khối ```json ... ``` và lời dẫn/lời kết quanh JSON."""
    s = str(text or "").strip()
    if not s:
        return ""
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    else:
        # Có fence mở mà không đóng (LLM bị cắt) -> lấy từ sau fence
        m2 = re.search(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n", s)
        if m2:
            s = s[m2.end():].strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    return s


def extract_json_block(text: str) -> str:
    """Cắt khối JSON cân bằng ngoặc đầu tiên ({...} hoặc [...]).

    Tôn trọng chuỗi trong nháy kép và escape, nên '}' nằm trong chuỗi không
    làm lệch phép đếm.
    """
    s = str(text or "")
    start = -1
    opener = ""
    for i, ch in enumerate(s):
        if ch in "{[":
            start = i
            opener = ch
            break
    if start < 0:
        return ""

    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    quote = ""
    escaped = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_str = False
            continue
        if ch in "\"'":
            in_str = True
            quote = ch
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    # Thiếu ngoặc đóng -> tự bù để vẫn cứu được dữ liệu
    return s[start:] + closer * max(depth, 0)


def repair_json(text: str) -> str:
    """Sửa các lỗi JSON phổ biến mà LLM hay mắc."""
    s = str(text or "")
    for bad, good in _SMART_MAP.items():
        s = s.replace(bad, good)
    # BOM / ký tự điều khiển lạ
    s = s.replace("\ufeff", "")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    # Comment JS
    s = re.sub(r"(?m)^\s*//.*$", "", s)
    s = re.sub(r"(?m)^\s*#.*$", "", s)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    # Hằng số kiểu Python/JS
    s = re.sub(r"\bNone\b", "null", s)
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNaN\b", "null", s)
    s = re.sub(r"\bInfinity\b", "null", s)
    # Giá trị không nháy: { kind: greeting } -> { kind: "greeting" }
    # (làm TRƯỚC khi đổi hằng số; loại trừ literal của JSON/Python)
    s = re.sub(
        r'([:\[,]\s*)((?!(?:true|false|null|None|True|False|NaN|Infinity)\b)'
        r'[A-Za-z_][A-Za-z0-9_\- ]*?)(\s*)(?=[,}\]])',
        r'\1"\2"\3',
        s,
    )
    # Key không có nháy: { type: "greeting" } -> { "type": "greeting" }
    s = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_\- ]*)\s*:', r'\1"\2":', s)
    # Dấu phẩy thừa trước } ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # Nháy đơn -> nháy kép (giữ nguyên nháy đơn bên trong chuỗi nháy kép)
    s = _single_to_double(s)
    # Ký tự điều khiển thật bên trong chuỗi -> dạng escape hợp lệ
    s = _escape_control_in_strings(s)
    return s


def _escape_control_in_strings(s: str) -> str:
    """Đổi xuống dòng/tab thật nằm TRONG chuỗi JSON thành \\n, \\t hợp lệ."""
    out = []
    in_str = False
    escaped = False
    for ch in s:
        if in_str:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                in_str = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
            continue
        if ch == '"':
            in_str = True
        out.append(ch)
    return "".join(out)


def _single_to_double(s: str) -> str:
    """Đổi 'value' thành "value" cho JSON, không đụng chuỗi đang là nháy kép."""
    out = []
    i = 0
    n = len(s)
    in_double = False
    while i < n:
        ch = s[i]
        if in_double:
            if ch == "\\" and i + 1 < n:
                out.append(s[i:i + 2])
                i += 2
                continue
            if ch == '"':
                in_double = False
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            # tìm nháy đơn đóng (không escape)
            j = i + 1
            buf = []
            closed = False
            while j < n:
                c = s[j]
                if c == "\\" and j + 1 < n:
                    buf.append(s[j:j + 2])
                    j += 2
                    continue
                if c == "'":
                    closed = True
                    break
                if c == '"':
                    buf.append('\\"')
                    j += 1
                    continue
                buf.append(c)
                j += 1
            if closed:
                out.append('"' + "".join(buf) + '"')
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_json_loose(text, default=None):
    """Parse JSON chịu lỗi. Trả về default nếu không cứu được."""
    if isinstance(text, (dict, list)):
        return text
    raw = str(text or "")
    if not raw.strip():
        return default

    candidates = []
    stripped = strip_code_fence(raw)
    for c in (raw.strip(), stripped):
        if c and c not in candidates:
            candidates.append(c)
    for base in list(candidates):
        blk = extract_json_block(base)
        if blk and blk not in candidates:
            candidates.append(blk)

    for cand in candidates:
        for attempt in (cand, repair_json(cand)):
            try:
                return json.loads(attempt)
            except Exception:
                pass

    # JSON kiểu Python
    for cand in candidates:
        for attempt in (cand, repair_json(cand)):
            try:
                v = ast.literal_eval(attempt)
                if isinstance(v, (dict, list)):
                    return v
            except Exception:
                pass
    return default


def as_list(value) -> list:
    """Ép về list. dict đơn lẻ -> [dict]. Chuỗi JSON -> list đã parse."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "data", "results", "events", "list", "output"):
            inner = value.get(key)
            if isinstance(inner, list):
                return inner
            if isinstance(inner, dict):
                return [inner]
        return [value]
    if isinstance(value, str):
        parsed = parse_json_loose(value, default=None)
        if parsed is not None and parsed is not value:
            return as_list(parsed)
    return []


def as_dict(value) -> dict:
    """Ép về dict. list 1 phần tử -> phần tử đó. Chuỗi JSON -> dict đã parse."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value:
        if isinstance(value[0], dict):
            return value[0]
    if isinstance(value, str):
        parsed = parse_json_loose(value, default=None)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
    return {}


def _first_key(d: dict, *names):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    lower = {str(k).lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in lower and lower[n.lower()] is not None:
            return lower[n.lower()]
    return None


def get_str(d, *names, default: str = "") -> str:
    """Lấy giá trị chuỗi đầu tiên có trong dict theo danh sách tên khoá."""
    v = _first_key(d if isinstance(d, dict) else {}, *names)
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v if x is not None)
    return str(v).strip()


def get_int(d, *names, default: int = 0) -> int:
    """Lấy giá trị int đầu tiên; chấp nhận cả chuỗi số."""
    v = _first_key(d if isinstance(d, dict) else {}, *names)
    if v is None:
        return default
    if isinstance(v, bool):
        return int(v)
    try:
        return int(float(str(v).strip().replace(",", ".")))
    except Exception:
        m = re.search(r"-?\d+", str(v))
        return int(m.group(0)) if m else default


def get_bool(d, *names, default: bool = False) -> bool:
    """Lấy giá trị bool; hiểu 'true/1/có/yes' và 'false/0/không/no'."""
    v = _first_key(d if isinstance(d, dict) else {}, *names)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y", "có", "co", "đúng"):
        return True
    if s in ("false", "0", "no", "n", "không", "khong", "sai"):
        return False
    return default
