# TEST-CONFIG-WIRE — Cấu hình phải tác động thật vào runtime

Mục đích: chứng minh `settings.apply()` thực sự đổi hành vi các module, không chỉ ghi file.

## Bug gốc đã sửa

`llm_client` đọc `src.config` (dòng `import src.config as c`), nhưng `settings.apply()`
lại set module tên `config`. Trong Python, `src.config` và `config` là **hai module object
khác nhau** khi cả hai đã được import → đổi LLM URL/key qua Settings không có tác dụng.

Sửa: `settings.apply()` set **cả hai** tên qua `importlib.import_module(name)`:

```python
for _name in ("src.config", "config"):
    try:
        _mod = importlib.import_module(_name)
        _mod.LLM_BASE_URL = ...
        _mod.LLM_MODEL = ...
        _mod.LLM_API_KEY = ...
        _mod.LLM_TIMEOUT_S = ...
    except Exception:
        pass
```

Đồng thời `llm_client.chat()` đọc hằng số **lúc gọi** (không bind lúc import):

```python
import src.config as c
url = f"{c.LLM_BASE_URL}/chat/completions"
timeout = float(getattr(c, "LLM_TIMEOUT_S", 20.0)) if timeout is None else timeout
```

## Bằng chứng (script chạy thật)

```text
$ python - <<'PY'
import sys; sys.path.insert(0,'src'); sys.path.insert(0,'.')
import settings, tts_client
import src.config as c
cfg = settings.get()
cfg['llm_base_url']='http://10.0.0.8:8888/v1'
cfg['llm_api_key']='sk-test-key-1234567890'
cfg['llm_model']='test-model-x'
cfg['voicestudio_url']='http://10.0.0.9:9999'
settings.apply(cfg)
print('src.config LLM_BASE_URL =', c.LLM_BASE_URL)
print('src.config LLM_MODEL    =', c.LLM_MODEL)
print('tts VOICE_URL           =', tts_client.VOICE_URL)
import config as c2
print('config LLM_BASE_URL     =', c2.LLM_BASE_URL)
print('same module? ', c is c2)
PY
```

Kết quả:

```text
src.config LLM_BASE_URL = http://10.0.0.8:8888/v1
src.config LLM_MODEL    = test-model-x
tts VOICE_URL           = http://10.0.0.9:9999
config LLM_BASE_URL     = http://10.0.0.8:8888/v1
same module?  False
```

`same module? False` chính là lý do bug tồn tại; cả hai giờ đều nhận giá trị mới.

## Bằng chứng qua .exe (frozen)

Trỏ LLM sang URL không tồn tại bằng config file → `doctor` chuyển LLM từ `OK` sang `FAIL`:

```text
  OK   VoiceStudio    : OK http://127.0.0.1:3900 v0.5.6 (15 voices)
  FAIL LLM            : FAIL RuntimeError: LLM chat failed: <urlopen error timed out>
[doctor] ket qua: CO VAN DE (LLM, Bridge)
EXIT 1
```

Chi tiết đầy đủ: [`TEST-BUILD.md`](TEST-BUILD.md) mục 3d.

## Test tự động

`tests/test_settings_wire.py` — **6 test**:

| Test | Kiểm chứng |
|---|---|
| `test_apply_sets_tts_client` | `VOICE_URL`, `TTS_TIMEOUT`, `VOICE_NAME` đổi theo config |
| `test_apply_sets_llm_in_both_module_objects` | cả `config` và `src.config` đều nhận URL/model/key |
| `test_llm_client_reads_config_at_call_time` | source `llm_client.chat` có `LLM_BASE_URL` + `import src.config as c` |
| `test_analyzer_configure_applies_cooldown_and_batch` | `configure(cooldown=1.0, max_batch=2)` → `get_batcher()` phản ánh đúng |
| `test_masked_hides_api_key` | `settings.masked()` che key, không lộ chuỗi bí mật |
| `test_config_path_writable_location` | config path ở `%APPDATA%`, không nằm trong thư mục app |

```text
$ python -m pytest tests/test_settings_wire.py -q
6 passed
```

Toàn bộ suite: `python -m pytest tests/ -q` → **37 passed**.

## Chưa làm / khi nào cần

- **Chưa validate kiểu dữ liệu chặt** (vd `llm_base_url` phải là URL hợp lệ): hiện chỉ coerce theo kiểu của DEFAULTS. Thêm pydantic-settings khi cần báo lỗi cấu hình rõ ràng cho người dùng cuối.
- **Chưa hot-reload cấu hình** cho process đang chạy: `run` đọc config lúc khởi động; đổi giữa chừng cần restart. Thêm khi cần chỉnh tham số khi đang live.
