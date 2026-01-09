# Auto Check Scheduler - Tự động kiểm phiếu định kỳ

## Tổng quan

Auto Check Scheduler là một background service tự động quét và kiểm phiếu mỗi 15 giây. Service này:

- ✅ Tự động quét các phiếu chưa kiểm trong polls đã bật auto check
- ✅ Tự động tiền xử lý nếu phiếu chưa được tiền xử lý
- ✅ Tự động gọi AI để kiểm phiếu
- ✅ Chạy trong background thread riêng, không ảnh hưởng các chức năng khác
- ✅ Xử lý tối đa 5 phiếu mỗi lần quét để tránh quá tải
- ✅ **Chỉ khởi động khi user bật toggle "Tự động kiểm phiếu"**

## Cách hoạt động

### 1. Khởi động thủ công từ Form

**Scheduler KHÔNG tự động khởi động khi server start.** 

Scheduler chỉ khởi động khi:
- User bật toggle "Tự động kiểm phiếu" ở form kiểm phiếu
- Có ít nhất 1 poll bật auto check

Scheduler sẽ tự động dừng khi:
- User tắt toggle và không còn poll nào bật auto check

### 2. Khởi động từ Form UI:

1. Vào form kiểm phiếu: `/counting/poll/<poll_id>/`
2. Bật toggle **"Tự động kiểm phiếu"**
3. Nhập số phiếu tối đa (hoặc để mặc định)
4. Toggle sẽ tự động:
   - Lưu cấu hình vào database
   - Khởi động scheduler nếu chưa chạy
   - Hiển thị trạng thái "Scheduler đang chạy (quét mỗi 15s)"

**Khi tắt toggle:**
- Nếu không còn poll nào bật auto check → Scheduler tự động dừng
- Nếu còn poll khác bật → Scheduler tiếp tục chạy

### 3. Luồng xử lý tự động

Mỗi 15 giây, scheduler sẽ:

1. **Quét polls có bật auto check**
   - Tìm `AIModelResult` có `auto_check_enabled=True`
   - Kiểm tra giới hạn `auto_check_max_ballots`

2. **Tìm phiếu chưa kiểm**
   - Lấy tối đa 5 phiếu có `is_checked=False` và có ảnh
   - Sắp xếp theo `ballot_id`

3. **Xử lý từng phiếu**:
   ```
   Kiểm tra tiền xử lý
       ↓ (Nếu chưa tiền xử lý)
   Tiền xử lý ảnh → Cắt ô
       ↓
   Kiểm tra đã kiểm chưa
       ↓ (Nếu chưa kiểm)
   Gọi YOLO API
       ↓
   Gọi TrOCR API (nếu config2)
       ↓
   Lưu kết quả kiểm phiếu
       ↓
   Tăng counter auto_check_processed
   ```

### 3. Bật/Tắt Auto Check

#### Từ Frontend (Form UI - **KHUYẾN KHÍCH**):

1. Vào `/counting/poll/<poll_id>/`
2. Bật/tắt toggle "Tự động kiểm phiếu"
3. Scheduler tự động khởi động/dừng

#### Từ API:

```javascript
// Bật auto check
fetch('/counting/poll/105/auto-check/toggle/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': csrfToken
    },
    body: new URLSearchParams({
        'auto_check_enabled': 'true',
        'auto_check_max_ballots': '100'  // Tối đa 100 phiếu, hoặc để trống = unlimited
    })
})
```

```javascript
// Lấy trạng thái
fetch('/counting/poll/105/auto-check/status/')
    .then(r => r.json())
    .then(data => {
        console.log('Auto check enabled:', data.auto_check_enabled);
        console.log('Đã xử lý:', data.auto_check_processed, '/', data.auto_check_max_ballots);
    });
```

#### Từ Database:

```python
from counting.models import AIModelResult

# Bật auto check cho poll 105
ai_result = AIModelResult.objects.filter(poll_id=105).order_by('-created_at').first()
ai_result.auto_check_enabled = True
ai_result.auto_check_max_ballots = 100  # hoặc None = unlimited
ai_result.save()
```

### 4. Quản lý Scheduler thủ công

```bash
# Xem trạng thái
python manage.py autocheck_scheduler --status

# Khởi động thủ công (nếu chưa chạy)
python manage.py autocheck_scheduler --start

# Thay đổi interval
python manage.py autocheck_scheduler --start --interval 30  # 30 giây

# Dừng scheduler
python manage.py autocheck_scheduler --stop
```

## Logs và Monitoring

### Log quan trọng:

```
[AUTO_CHECK_SCHEDULER] Poll 105: Found 5 unchecked ballots
[AUTO_CHECK_SCHEDULER] Ballot 123: Starting processing
[AUTO_CHECK_SCHEDULER] Ballot 123: Starting preprocessing
[AUTO_CHECK_SCHEDULER] Ballot 123: Preprocessing completed
[AUTO_CHECK_SCHEDULER] Ballot 123: Starting auto check
[AUTO_CHECK_SCHEDULER] Ballot 123: Auto check completed (5/100)
```

### Log khi đạt giới hạn:

```
[AUTO_CHECK_SCHEDULER] Poll 105: Reached limit 100, disabling auto check
```

### Log khi có lỗi:

```
[AUTO_CHECK_SCHEDULER] Ballot 123: Preprocessing failed - Không tìm thấy markers
[AUTO_CHECK_SCHEDULER] Ballot 124: YOLO failed
[AUTO_CHECK_SCHEDULER] Error checking ballots: ...
```

## Cấu hình

### Thay đổi interval (mặc định 15 giây):

Sửa file `counting/apps.py`:

```python
# Thay đổi interval sang 30 giây
start_scheduler(interval=30)
```

### Thay đổi số phiếu xử lý mỗi lần (mặc định 5):

Sửa file `counting/auto_check_scheduler.py`, dòng:

```python
].order_by('ballot_id')[:5]  # Mỗi lần xử lý tối đa 5 phiếu
```

Thay `:5` thành số khác (VD: `:10` để xử lý 10 phiếu mỗi lần)

### Thay đổi delay giữa các phiếu (mặc định 0.5s):

Sửa file `counting/auto_check_scheduler.py`, dòng:

```python
time.sleep(0.5)  # Delay nhỏ giữa các ballot
```

## Lưu ý quan trọng

1. **Scheduler chạy background**: Không block các request HTTP
2. **Mỗi phiếu 1 thread**: Các phiếu được xử lý song song
3. **Tự động tắt khi đạt giới hạn**: Khi `auto_check_processed >= auto_check_max_ballots`
4. **Chỉ xử lý phiếu có ảnh**: Phiếu không có ảnh sẽ bị bỏ qua
5. **Không xử lý lại phiếu đã kiểm**: Kiểm tra `is_checked=False`

## Workflow hoàn chỉnh

### Upload từ Mobile App:
```
Mobile upload phiếu
    ↓
API verify chữ ký
    ↓
Làm phẳng ảnh + đọc QR
    ↓
Lưu Ballot vào DB
    ↓
Signal: Tự động tiền xử lý (nếu bật auto check)
    ↓
Signal: Tự động kiểm phiếu (nếu bật auto check)
```

### Scheduler quét định kỳ:
```
Mỗi 15 giây
    ↓
Tìm polls có auto_check_enabled=True
    ↓
Tìm phiếu chưa kiểm (is_checked=False)
    ↓
Xử lý từng phiếu (tiền xử lý + kiểm phiếu)
    ↓
Tăng counter
    ↓
Tự động tắt khi đạt giới hạn
```

## Troubleshooting

### Scheduler không chạy?

1. Kiểm tra log khi start server
2. Chạy thủ công: `python manage.py autocheck_scheduler --start`
3. Kiểm tra status: `python manage.py autocheck_scheduler --status`

### Phiếu không được tự động kiểm?

1. Kiểm tra `auto_check_enabled=True` trong database
2. Kiểm tra phiếu có ảnh không (`ballot_image IS NOT NULL`)
3. Kiểm tra đã đạt giới hạn chưa (`auto_check_processed < auto_check_max_ballots`)
4. Xem logs để biết lỗi cụ thể

### Performance vấn đề?

1. Tăng interval: `--interval 30` (30 giây thay vì 15 giây)
2. Giảm số phiếu mỗi lần: Sửa `[:5]` → `[:3]`
3. Tăng delay giữa phiếu: `time.sleep(1.0)` thay vì `0.5`

## API Endpoints

- `POST /counting/poll/<poll_id>/auto-check/toggle/` - Bật/tắt auto check (tự động start/stop scheduler)
- `GET /counting/poll/<poll_id>/auto-check/status/` - Lấy trạng thái auto check
- `GET /counting/scheduler/status/` - Lấy trạng thái scheduler (running/stopped, số poll active)
