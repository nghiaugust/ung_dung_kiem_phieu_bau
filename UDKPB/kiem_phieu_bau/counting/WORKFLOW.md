# Quy trình tự động xử lý phiếu bầu

## Tổng quan

Hệ thống có 3 bước xử lý TUẦN TỰ cho mỗi phiếu bầu:
1. **Upload** (API) - Lưu ảnh phiếu bầu
2. **Preprocessing** (Background) - Tiền xử lý ảnh
3. **Auto Check** (Background) - Kiểm phiếu bằng AI

**QUAN TRỌNG:**
- Mỗi bước CHỈ CHẠY SAU KHI bước trước đã COMMIT thành công
- Các bước 2 và 3 chạy trong **background thread riêng biệt**
- Upload API trả về NGAY LẬP TỨC, không đợi xử lý
- Nhiều phiếu có thể upload đồng thời và xử lý song song

## Chi tiết luồng xử lý

### Bước 1: UPLOAD (Đồng bộ - Main Thread)
```
[Client] POST /ballot/upload
    ↓
[Django] Save Ballot to DB
    ↓
[Django] COMMIT transaction
    ↓
[Client] ← JSON Response (10-50ms) ✅
    ↓
[Signal] Lên lịch preprocessing (không block)
```

**File:** `ballot/views.py` hoặc API upload
**Thời gian:** < 100ms
**Database:** INSERT vào `ballot`

### Bước 2: PREPROCESSING (Bất đồng bộ - Background Thread)
```
[Signal] post_save(Ballot)
    ↓
[Signal] transaction.on_commit() 
    ↓
[Thread] Start background thread
    ↓
[Worker] Kiểm tra điều kiện:
         - Có bật auto check?
         - Đã đạt giới hạn?
         - Đã preprocessing chưa?
    ↓
[Worker] process_single_ballot_wrapper()
         - Đọc QR code
         - Detect markers
         - Warp perspective
         - Crop cells
    ↓
[Worker] COMMIT PreprocessedBallot
    ↓
[Signal] Lên lịch auto check (không block)
```

**File:** `preprocessing/signals.py`
**Thời gian:** 2-10 giây (tùy kích thước ảnh)
**Database:** INSERT vào `preprocessed_ballot`, `ballot_cell`

### Bước 3: AUTO CHECK (Bất đồng bộ - Background Thread)
```
[Signal] post_save(PreprocessedBallot)
    ↓
[Signal] transaction.on_commit()
    ↓
[Thread] Start background thread
    ↓
[Worker] Kiểm tra điều kiện:
         - Có bật auto check?
         - Đã kiểm chưa?
         - Đã đạt giới hạn?
    ↓
[Worker] Gọi AI APIs:
         - TrOCR: Nhận diện tên
         - YOLO: Detect dấu X
    ↓
[Worker] COMMIT kết quả:
         - UPDATE AIModelResult
         - UPDATE Ballot.is_checked
         - INSERT BallotSelection
    ↓
[Worker] Kiểm tra giới hạn
         - Nếu đủ → Tắt auto check
```

**File:** `counting/signals.py`
**Thời gian:** 5-15 giây (tùy số dòng + API)
**Database:** UPDATE `ai_model_result`, `ballot`, INSERT `ballot_selection`

## Timeline ví dụ

```
Time  | Ballot 1              | Ballot 2              | Ballot 3
------|-----------------------|-----------------------|----------------------
0ms   | Upload started        |                       |
10ms  | ← Response ✅          |                       |
100ms | Preprocessing...      | Upload started        |
110ms |                       | ← Response ✅          |
2s    | Preprocessing done ✅  | Preprocessing...      | Upload started
2.01s | Auto check...         |                       | ← Response ✅
2.2s  |                       | Preprocessing done ✅  | Preprocessing...
2.21s |                       | Auto check...         |
7s    | Auto check done ✅     |                       |
9s    |                       | Auto check done ✅     | Preprocessing done ✅
9.01s |                       |                       | Auto check...
14s   |                       |                       | Auto check done ✅
```

## Đảm bảo thứ tự và không block

### 1. Sử dụng `transaction.on_commit()`
```python
@receiver(post_save, sender=Ballot)
def auto_preprocess_ballot_on_upload(sender, instance, created, **kwargs):
    # Chỉ lên lịch, không chạy ngay
    transaction.on_commit(lambda: _start_auto_preprocess_background(instance.ballot_id))
```

**Lợi ích:**
- Background task chỉ chạy SAU KHI transaction commit
- Tránh xử lý data chưa tồn tại trong DB
- Upload response trả về ngay lập tức

### 2. Sử dụng Threading
```python
def _start_auto_preprocess_background(ballot_id):
    thread = threading.Thread(
        target=_auto_preprocess_worker,
        args=(ballot_id,),
        name=f"AutoPreprocess-{ballot_id}",
        daemon=True
    )
    thread.start()
```

**Lợi ích:**
- Mỗi ballot có thread riêng
- Không block main thread (upload)
- Ballots khác nhau xử lý song song

### 3. Lấy lại instance trong thread
```python
def _auto_preprocess_worker(ballot_id):
    # QUAN TRỌNG: Query lại từ DB trong thread mới
    ballot = Ballot.objects.get(ballot_id=ballot_id)
    # Đảm bảo có connection riêng, không xung đột
```

**Lợi ích:**
- Thread có database connection riêng
- Tránh shared state giữa threads
- An toàn với concurrent requests

## Logging và Monitoring

Mỗi bước có logging rõ ràng:

```
[WORKFLOW] Ballot 123: Started preprocessing thread
[WORKFLOW] Ballot 123: Step 2 - Preprocessing started
[WORKFLOW] Ballot 123: Processing...
[WORKFLOW] Ballot 123: Step 2 - Preprocessing completed in 3.45s
[WORKFLOW] Ballot 123: Next → Auto check will start after commit

[WORKFLOW] Preprocessed 456: Started auto check thread
[WORKFLOW] Ballot 123: Step 3 - Auto check started
[WORKFLOW] Ballot 123: Processing 10 rows...
[WORKFLOW] Ballot 123: Saved results (1/100)
[WORKFLOW] Ballot 123: Step 3 - Auto check completed in 8.23s
[WORKFLOW] Ballot 123: === WORKFLOW COMPLETED ===
```

## Xử lý lỗi

Mỗi thread có try-catch riêng:

```python
try:
    # Xử lý
    elapsed = time.time() - start_time
    print(f"[WORKFLOW] Ballot {ballot_id}: Step X completed in {elapsed:.2f}s")
except Exception as e:
    elapsed = time.time() - start_time
    print(f"[WORKFLOW] Ballot {ballot_id}: Step X FAILED in {elapsed:.2f}s")
    print(f"[WORKFLOW ERROR] {e}")
```

**Lợi ích:**
- Lỗi ở 1 ballot không ảnh hưởng ballots khác
- Có thông tin thời gian xử lý
- Dễ debug và trace

## Cấu hình

Auto check có thể bật/tắt và giới hạn:

```python
AIModelResult:
    - auto_check_enabled: True/False
    - auto_check_max_ballots: 100 (hoặc None = unlimited)
    - auto_check_processed: 0 (đếm số phiếu đã kiểm)
```

Khi đạt giới hạn:
```
[WORKFLOW] Poll 5: Reached limit 100, disabling auto check
```

## FAQ

**Q: Upload có bị chậm khi bật auto check không?**
A: KHÔNG. Upload vẫn trả về trong < 100ms. Xử lý chạy background sau.

**Q: Nhiều người upload cùng lúc có bị conflict không?**
A: KHÔNG. Mỗi ballot có thread riêng, không ảnh hưởng lẫn nhau.

**Q: Làm sao biết phiếu đã được xử lý xong?**
A: Kiểm tra `ballot.is_checked = True` hoặc reload trang để xem số đã kiểm.

**Q: Nếu server tắt giữa chừng thì sao?**
A: Phiếu chưa xử lý xong sẽ bỏ qua. Có thể xử lý lại bằng tay sau.
