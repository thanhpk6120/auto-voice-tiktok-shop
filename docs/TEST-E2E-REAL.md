# TEST E2E REAL — Auto Voice TikTok Shop (chạy thật, có bằng chứng)

Thời điểm chạy: **2026-10-17 ~14:43–14:56** (giờ máy, Windows).
Môi trường: Python 3.11.15, Windows, VoiceStudio backend v0.5.6 ở `http://127.0.0.1:3900` (device `cuda`),
loa ra `G27Q (NVIDIA High Definition Audio)` (index=4), event bridge `ws://127.0.0.1:8765`.

Thành phần thật đã dùng:
- TTS thật: VoiceStudio `POST /v1/audio/speech` (engine `omnivoice`), trả WAV 24 kHz mono.
- LLM thật: `http://192.168.1.68:20130/v1`, model `claude-sonnet-5` (dùng cho analyzer trả lời chat).
- Phát thật: `sounddevice` + `numpy` (ngắt được giữa chừng); `winsound` là đường lui.
- Bridge thật: `src/event_bridge.py serve --port 8765` (WebSocket, 2 vai trò `role=source` / `role=app`).

---

## 1. `python src/app.py doctor`

```text
$ python src/app.py doctor
[doctor] Auto Voice TikTok Shop - chan doan
  OK   VoiceStudio    : OK http://127.0.0.1:3900 v0.5.6 (15 voices)
  OK   LLM            : OK http://192.168.1.68:20130/v1 model=claude-sonnet-5 latency=3685ms reply='OK. Sẵn sàng. Cần gì?'
  OK   Audio output   : G27Q (NVIDIA High Definition Au (index=4)
  OK   Bridge         : OK ws://127.0.0.1:8765/ws?role=app events=26 trong 2.9s
  OK   Audio queue    : OK uu tien dung p1 truoc p3 (order=[1, 3]), size 0->2->0
  OK   Event simulator: OK 10 event(s) sinh duoc
[doctor] ket qua: TAT CA OK
```

- Exit code: `0` (log đầy đủ: `out/e2e_doctor.log`).
- Lưu ý: khi bridge chưa bật, mục `Bridge` báo `FAIL ... ConnectionRefusedError [WinError 10061]` và exit code `1`
  — đúng như thiết kế (doctor không che lỗi thành phần).

## 2. `python src/app.py simulate --no-play`

```text
$ python src/app.py simulate --no-play
Starting simulation... (no_play=True)
event=gift -> speak_text='Cảm ơn Hoàng Nam đã tặng Hoa hồng!' -> wav=tts_1792223188727_5066aa2a.wav -> priority=1 -> queue-size=1 [no-play]
event=chat -> speak_text='Dạ shop chưa ghi rõ size trong mô tả áo này. Anh/chị cho em chiều cao, cân nặng để em check size XL còn hàng không nhé? Giá 150k, tồn 120 áo.' -> wav=tts_1792223195749_fa18591f.wav -> priority=2 -> queue-size=2 [no-play]
VOICESTUDIO_OK=false fallback (HTTPError: HTTP Error 429: Too Many Requests)
event=gift -> speak_text='Cảm ơn Thu Trang đã tặng Hoa hồng!' -> wav=tts_1792223203166_dd2832e5.wav -> priority=1 -> queue-size=3 [no-play]
event=chat -> speak_text='Dạ pin dùng liên tục 6 tiếng ạ, bass đập rung tai, chống nước IPX4. Giá chỉ 450k, còn 200 cái, chốt ngay kẻo lỡ nha cả nhà!' -> wav=tts_1792223208749_5991c8ca.wav -> priority=2 -> queue-size=4 [no-play]
event=chat -> speak_text='Còn hàng ạ, còn 45 hộp. Kem gel 350.000đ, thấm nhanh không bết, cấp nước 24h. Chốt ngay không mất ưu đãi!' -> wav=tts_1792223215049_0adf50b5.wav -> priority=2 -> queue-size=5 [no-play]
event=order -> speak_text='Cảm ơn Lan Anh đã chốt đơn!' -> wav=tts_1792223217644_e3032f21.wav -> priority=1 -> queue-size=6 [no-play]
event=join(flushed) -> speak_text='Hello Minh Tuấn, Lan Anh, Phương Thảo, Thu Trang!' -> wav=tts_1792223219070_b877393b.wav -> queue-size=7
Simulation done. queue-size=7
Drain order (priority): p1:gift, p1:gift, p1:order, p2:sales, p2:sales, p2:sales, p3:greeting
```

- Exit code `0` (log: `out/e2e_simulate_noplay.log`).
- **1 lần fallback có chủ đích quan sát được**: VoiceStudio trả `HTTP 429 Too Many Requests` → `tts_client` tự
  sinh sine WAV để pipeline không gãy. Đây là hành vi mong muốn, không phải lỗi app.
- Thứ tự xả hàng đợi xác nhận ưu tiên: **p1 (gift/order) → p2 (sales/chat) → p3 (greeting)**.

## 3. `python src/app.py run` — vòng lặp thật, nhận event từ bridge

### 3a. `--no-play` (không phát tiếng)

```text
$ python src/app.py run --no-play --max-events 8
[run] bat dau (no_play=True, seconds=vo han). Ctrl+C de dung.
[run] nguon event: bridge ws://127.0.0.1:8765/ws?role=app
event=order -> speak_text='Cảm ơn Minh Tuấn đã chốt đơn!' -> wav=tts_1792223105359_dd17db5e.wav -> priority=1 -> queue-size=1 [no-play]
event=order -> speak_text='Cảm ơn Hoàng Nam đã chốt đơn!' -> wav=tts_1792223105357_02e18a5f.wav -> priority=1 -> queue-size=1 [no-play]
event=chat -> speak_text='Dạ áo thun Cotton Compact hôm nay 150.000đ ạ. Áo thun siêu mát, mặc cực sướng, anh chị chốt luôn giá tốt hôm nay nhé!' -> wav=tts_1792223107615_41374a00.wav -> priority=2 -> queue-size=1 [no-play]
event=order -> speak_text='Cảm ơn Khánh Linh đã chốt đơn!' -> wav=tts_1792223108106_0d715200.wav -> priority=1 -> queue-size=1 [no-play]
event=chat -> speak_text='Có freeship không ạ?' -> wav=tts_1792223108600_7a6711c1.wav -> priority=3 -> queue-size=1 [no-play]
event=order -> speak_text='Cảm ơn Ngọc Mai đã chốt đơn!' -> wav=tts_1792223110291_76c169f7.wav -> priority=1 -> queue-size=1 [no-play]
event=chat -> speak_text='Dạ áo thun nam Cotton Compact giá 150.000đ ạ. Còn 120 áo, cotton co giãn 4 chiều, mặc mát. Anh chị chốt luôn hôm nay em giữ giá tốt nhé!' -> wav=tts_1792223115930_40d51623.wav -> priority=2 -> queue-size=1 [no-play]
[run] flush greeting: 'Chào Phương Thảo!'
=== RUN SUMMARY ===
events_nhan=9 cau_da_doc=8
tts: ok=9 fallback=0 engine=omnivoice
tts_latency: min=0ms max=5316ms avg=3584ms
queue: {'played': 9, 'interrupted': 0, 'dropped_overflow': 0, 'errors': 0} qsize_con_lai=0
play: no-play (khong phat tieng) device=G27Q (NVIDIA High Definition Au (index=4)
```

- Exit code `0` (log: `out/e2e_run_noplay.log`).
- Số event nhận (9) > số câu đọc (8) vì event `join` được **gộp batch** (chưa đủ cửa sổ cooldown nên không tốn TTS).

### 3b. Đường dữ liệu thật của extension/UI (`role=source` → bridge → `role=app`)

Bridge chạy **không** `--sim`; client đóng vai `ui/index.html` (cùng URL `ws://127.0.0.1:8765/ws?role=source`) gửi 3 event,
`app.py run` nhận đúng nguyên văn từng event:

```text
$ python src/app.py run --no-play --max-events 3
[run] bat dau (no_play=True, seconds=vo han). Ctrl+C de dung.
[run] nguon event: bridge ws://127.0.0.1:8765/ws?role=app
event=order -> speak_text='Cảm ơn UI Hoa đã chốt đơn!' -> wav=tts_1792223392808_505c880f.wav -> priority=1 -> queue-size=1 [no-play]
event=gift -> speak_text='Cảm ơn UI Nam đã tặng Hoa hồng!' -> wav=tts_1792223393309_ccd69beb.wav -> priority=1 -> queue-size=1 [no-play]
event=chat -> speak_text='Dữ liệu sản phẩm chưa ghi size, em kiểm tra kho rồi báo ngay. Áo cotton compact 150k, còn 120 cái, anh/chị để lại size nhé.' -> wav=tts_1792223400956_f919f7be.wav -> priority=2 -> queue-size=1 [no-play]
=== RUN SUMMARY ===
events_nhan=3 cau_da_doc=3
tts: ok=3 fallback=0 engine=omnivoice
tts_latency: min=2190ms max=2313ms avg=2270ms
queue: {'played': 3, 'interrupted': 0, 'dropped_overflow': 0, 'errors': 0} qsize_con_lai=0
play: no-play (khong phat tieng) device=G27Q (NVIDIA High Definition Au (index=4)
```

→ Xác nhận fan-out bridge hoạt động: `user="UI Hoa"`, `user="UI Nam"`, `text="Áo thun cotton có size XL không shop?"`
(chat) đều đến đúng analyzer.

### 3c. Phát tiếng thật ra loa (không `--no-play`)

```text
$ python src/app.py run --max-events 3
[run] bat dau (no_play=False, seconds=vo han). Ctrl+C de dung.
[run] nguon event: bridge ws://127.0.0.1:8765/ws?role=app
event=order -> speak_text='Cảm ơn Minh Tuấn đã chốt đơn!' -> wav=tts_1792223230586_dd17db5e.wav -> priority=1 -> queue-size=1
event=order -> speak_text='Cảm ơn Minh Tuấn đã chốt đơn!' -> wav=tts_1792223230585_dd17db5e.wav -> priority=1 -> queue-size=1
event=chat -> speak_text='Còn 45 hộp, giá 350.000đ. Gel thẩm thấu nhanh, cấp nước 24h, da căng bóng, hợp mọi loại da. Chốt luôn em giữ đơn?' -> wav=tts_1792223233090_425797c7.wav -> priority=2 -> queue-size=1
=== RUN SUMMARY ===
events_nhan=3 cau_da_doc=3
tts: ok=3 fallback=0 engine=omnivoice
tts_latency: min=2378ms max=2434ms avg=2400ms
queue: {'played': 3, 'interrupted': 0, 'dropped_overflow': 0, 'errors': 0} qsize_con_lai=0
play: da phat ra loa device=G27Q (NVIDIA High Definition Au (index=4)
```

Kiểm chứng WAV sinh ra là audio thật (không phải fallback sine — file 1 kHz sine chỉ ~31 KB/giây độ dài cố định 1s):

| WAV | Thời lượng | Kích thước |
|---|---|---|
| `tts_1792223230586_dd17db5e.wav` | 1.98 s | 95 084 B |
| `tts_1792223230585_dd17db5e.wav` | 2.08 s | 99 884 B |
| `tts_1792223233090_425797c7.wav` | 8.33 s | 399 884 B |

### 3d. Latency TTS thật (VoiceStudio `omnivoice`, qua bridge, có LLM cho câu chat)

| Lần chạy | min | avg | max | ghi chú |
|---|---|---|---|---|
| `run --no-play --max-events 8` | 0 ms* | 3584 ms | 5316 ms | *join gộp batch không gọi TTS |
| `run --no-play --max-events 3` (UI path) | 2190 ms | **2270 ms** | 2313 ms | event order/gift/chat |
| `run --max-events 3` (phát thật) | 2378 ms | **2400 ms** | 2434 ms | 3 câu, đã phát ra loa |
| `run --no-play --max-events 8` (lần sau, tải cao) | 1797 ms | 4794 ms | 8363 ms | TTS lần đầu phải load model + LLM chậm |

- **Latency TTS thật điển hình: ~2.3–2.4 s/câu** (đã warmup). Lần đầu trong phiên có thể tới ~5–8 s do load model.
- Thời gian 1 event `join` không có TTS = 0 ms (được gộp batch).
- VoiceStudio có rate limit (`HTTP 429`) khi gọi dồn dập → đôi khi 1 câu phải dùng fallback sine (~1 s).

## 4. Ngắt giữa chừng khi priority=1 chen ngang (phát audio thật)

Kịch bản: đang phát câu p2 dài **11.92 s**, chèn câu p1 → câu p2 bị ngắt ngay, câu p1 phát trọn.
Log: `out/e2e_interrupt.log`.

```text
# file dai (p2): out\tts_1792223201003_2dd53728.wav (11.92s)
# file ngan (p1): out\tts_1792223203166_dd2832e5.wav (1.00s)
# dang phat: {'kind': 'sales', 'priority': 2, 'speak_text': 'cau tu van dai', 'wav': WindowsPath('out/tts_1792223201003_2dd53728.wav')}
# log: [('tts_1792223201003_2dd53728.wav', 1.7, False), ('tts_1792223203166_dd2832e5.wav', 1.09, True)]
# stats: {'played': 1, 'interrupted': 1, 'dropped_overflow': 0, 'errors': 0}
```

→ File 11.92 s dừng ở **1.7 s** (trả `False` = bị ngắt), câu p1 phát đủ 1.09 s (trả `True`).
Hành vi đã chọn: câu bị ngắt **bỏ luôn** (không phát lại) để giảm trễ; câu p1 không bị ngắt bởi p2.

## 5. `python -m pytest tests/ -q`

```text
$ python -m pytest tests/ -q
....................                                                     [100%]
20 passed in 28.93s
```

Exit code `0` (log: `out/e2e_pytest.log`). Bao gồm test cho: pipeline analyzer/queue cũ,
`test_audio_queue.py` (worker, thứ tự ưu tiên, interrupt p1, dry-run, overflow),
`test_event_bridge.py` (normalize, hub, round-trip server ↔ client),
`test_bridge_parse.py` (parse DOM dashboard → event đúng schema, qua 3 fixture HTML thật).

---

## 6. Tổng hợp kết quả

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| `doctor` (VoiceStudio/LLM/loa/bridge/queue/sim) | PASS (exit 0) | §1, `out/e2e_doctor.log` |
| `simulate --no-play` (thứ tự ưu tiên p1→p2→p3) | PASS | §2, `out/e2e_simulate_noplay.log` |
| `run` nhận event thật từ bridge (`role=app`) | PASS | §3a, §3b |
| Fan-out extension/UI (`role=source`) → app | PASS | §3b |
| Phát tiếng thật ra loa (WAV 24 kHz VoiceStudio) | PASS | §3c |
| Interrupt p1 khi đang phát p2 | PASS | §4, `out/e2e_interrupt.log` |
| `pytest tests/ -q` | PASS (20 passed) | §5, `out/e2e_pytest.log` |
| TTS fallback khi VoiceStudio lỗi/429 | PASS (có chủ đích) | §2 |

## 7. Hạn chế còn lại (ghi rõ, không che)

- **Extension chưa được chạy trên dashboard TikTok Shop thật**: selector DOM (`data-e2e`, class `comment-item`…)
  viết theo cấu trúc hiện tại + 3 fixture HTML mô phỏng; chưa xác minh trên URL live vì cần tài khoản seller
  và phiên live thật. Đường ống phía sau extension (bridge → app → TTS → loa) đã được test thật.
- **VoiceStudio cần warmup**: lần synthesize đầu trong phiên ~5–8 s; các câu sau ~2.3–2.4 s.
- **429 rate limit** từ VoiceStudio khi gọi dồn dập → câu đó rơi vào fallback sine 1 s.
- **`run` mặc định chạy vô hạn** (đúng thiết kế live): dừng bằng `Ctrl+C`, hoặc dùng `--seconds`/`--max-events` để tự dừng.
- Chưa có khoá chống trùng khi nhiều app consumer cùng nghe 1 bridge (fan-out gửi cho mọi client `role=app`).

---

## 4. Fix bug: doctor treo vo han (da sua)

**Trieu chung:** `python src/app.py doctor` treo > 250s, phai kill.

**Root cause:** `_check_bridge()` trong `src/app.py` chi kiem tra deadline (`window`) o **ben trong** loop body:

```python
for _ in bridge_mod.iter_events(url, stop_event=stop, open_timeout=3.0, recv_timeout=0.5):
    n += 1
    if (time.monotonic() - t0) >= window:   # chi chay khi CO event
        stop.set()
        break
```

`iter_events()` la generator block o `ws.recv()`. Khi bridge song nhung khong ban event nao (khong co client gui vao), loop body khong bao gio chay => `stop.set()` khong bao gio duoc goi => treo vinh vien.

**Fix:** dat deadline bang `threading.Timer(window, stop.set)` truoc khi vao loop, cancel trong `finally`.

**Bang chung sau fix:**

```text
$ python src/app.py doctor
[doctor] Auto Voice TikTok Shop - chan doan
  OK   VoiceStudio    : OK http://127.0.0.1:3900 v0.5.6 (15 voices)
  OK   LLM            : OK http://192.168.1.68:20130/v1 model=claude-sonnet-5 latency=4435ms reply='OK. San sang. Can lam gi?'
  OK   Audio output   : G27Q (NVIDIA High Definition Au (index=4)
  OK   Bridge         : OK ws://127.0.0.1:8765/ws?role=app events=0 trong 2.1s
  OK   Audio queue    : OK uu tien dung p1 truoc p3 (order=[1, 3]), size 0->2->0
  OK   Event simulator: OK 10 event(s) sinh duoc
[doctor] ket qua: TAT CA OK
```

- Thoi gian: **9.4s** (truoc do treo > 250s), exit code **0**.
- `python -m pytest tests/ -q` => **26 passed**.

### Trieu chung phu: bridge cu chiem port 8765

`run_bridge.py` chay lan 2 bao `OSError: [Errno 10048] only one usage of each socket address` vi tien trinh bridge cu con song (zombie). Xu ly: kill PID dang LISTENING tren 8765 roi chay lai. Nen `--port` khac hoac dam bao kill truoc khi restart.
