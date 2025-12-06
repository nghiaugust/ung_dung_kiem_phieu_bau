# Security App - Cryptographic Operations for Ballot QR Code

## Tổng quan

App `security` cung cấp các chức năng mã hóa sử dụng **RSA Digital Signature (2048-bit)** để xác thực phiếu bầu qua QR code.

## Cấu trúc

```
security/
├── __init__.py
├── apps.py
├── admin.py
├── models.py           # Không có model riêng
├── tests.py
├── crypto_utils.py     # Core cryptographic functions
├── views.py            # API endpoints
└── urls.py             # URL routing
```

## Tính năng chính

### 1. Generate Key Pair cho Poll

- Tạo RSA key pair (private + public key) cho mỗi cuộc bỏ phiếu
- Private key dùng để sign phiếu khi in
- Public key dùng để verify trên mobile app

### 2. Sign Ballot QR

- Tạo digital signature cho mỗi phiếu bầu
- Payload bao gồm: poll_id, ballot_id, timestamp, salt
- Signature được lưu vào database

### 3. Verify Ballot QR

- Xác thực phiếu bầu qua signature
- Kiểm tra tính toàn vẹn dữ liệu
- Phát hiện phiếu giả mạo

### 4. Batch Operations

- Sign nhiều phiếu cùng lúc
- Tối ưu cho việc in hàng loạt

## API Endpoints

### 1. Generate Keys cho Poll

```http
POST /security/poll/<poll_id>/generate-keys/
Authorization: Required (login)
Permission: Only poll creator or admin

Response:
{
  "success": true,
  "public_key": "base64_encoded_key...",
  "key_generated_at": "2025-12-05T10:30:00Z"
}
```

### 2. Get Public Key

```http
GET /security/poll/<poll_id>/public-key/

Response:
{
  "success": true,
  "poll_id": 1,
  "public_key": "base64_encoded_key...",
  "key_generated_at": "2025-12-05T10:30:00Z"
}
```

### 3. Sign Ballot

```http
POST /security/ballot/<ballot_id>/sign/
Authorization: Required (login)

Body (optional):
{
  "salt": "custom_salt"
}

Response:
{
  "success": true,
  "signature": "base64_signature...",
  "qr_data": "{\"s\":\"...\",\"p\":1,\"b\":123}",
  "payload": {
    "poll_id": 1,
    "ballot_id": 123,
    "timestamp": "2025-12-05T10:30:00Z",
    "salt": "random_hex"
  }
}
```

### 4. Verify Ballot (Public)

```http
POST /security/ballot/verify/

Body:
{
  "poll_id": 1,
  "ballot_id": 123,
  "signature": "base64_signature..."
}

Response:
{
  "success": true,
  "valid": true,
  "message": "Phiếu hợp lệ",
  "ballot": {...},
  "poll": {
    "public_key": "..."
  }
}
```

### 5. Batch Sign Ballots

```http
POST /security/poll/<poll_id>/batch-sign/
Authorization: Required (login)

Body:
{
  "ballot_ids": [123, 124, 125, ...]
}

Response:
{
  "success": true,
  "total": 10,
  "signed": 8,
  "already_signed": 2,
  "failed": 0,
  "results": [...]
}
```

## Sử dụng Crypto Utils

### Import

```python
from security.crypto_utils import (
    CryptoService,
    generate_keys,
    sign_ballot,
    verify_ballot
)
```

### Generate Key Pair

```python
private_key_b64, public_key_b64 = generate_keys()
```

### Sign Ballot

```python
signature, payload, qr_data = sign_ballot(
    poll_id=1,
    ballot_id=123,
    private_key_b64=private_key
)
```

### Verify Signature

```python
is_valid = verify_ballot(
    signature_b64=signature,
    payload_dict=payload,
    public_key_b64=public_key
)
```

## QR Code Format

Format tối giản để QR code nhỏ gọn:

```json
{
  "s": "base64_signature",
  "p": 1, // poll_id
  "b": 123 // ballot_id
}
```

## Workflow

### Khi in phiếu:

1. Admin tạo Poll
2. Gọi API generate keys cho Poll
3. Tạo Ballot records
4. Gọi API sign cho từng Ballot (hoặc batch)
5. Lấy `qr_data` và tạo QR code
6. In QR code lên phiếu

### Khi scan phiếu (Mobile App):

1. Scan QR code → parse JSON
2. Extract: signature, poll_id, ballot_id
3. Gọi API verify với 3 thông tin trên
4. Server trả về payload + public_key
5. App verify signature locally (optional, for extra security)
6. Hiển thị kết quả: Valid ✓ hoặc Invalid ✗

## Security Features

✅ **RSA 2048-bit**: Đủ an toàn cho ballot verification
✅ **Digital Signature**: Không thể giả mạo signature mà không có private key
✅ **Canonical JSON**: Serialization deterministic để đảm bảo signature consistency
✅ **Salt**: Mỗi phiếu có signature unique
✅ **Timestamp**: Track thời gian tạo signature
✅ **PSS Padding**: An toàn hơn PKCS1v15

## Requirements

Cần cài đặt thư viện:

```bash
pip install cryptography
```

## Database Schema Changes

### Poll Model

- `private_key`: TextField (Base64 encoded RSA private key)
- `public_key`: TextField (Base64 encoded RSA public key)
- `key_generated_at`: DateTimeField

### Ballot Model

- `qr_signature`: CharField(max_length=1024) - Base64 encoded signature
- `qr_generated_at`: DateTimeField
- `qr_payload`: JSONField - Original payload for verification

## Migration

Chạy migration để thêm các trường mới:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Testing

```python
# Test generate keys
from security.crypto_utils import generate_keys
private_key, public_key = generate_keys()
print(f"Private key length: {len(private_key)}")
print(f"Public key length: {len(public_key)}")

# Test sign and verify
from security.crypto_utils import sign_ballot, verify_ballot
signature, payload, qr_data = sign_ballot(1, 123, private_key)
is_valid = verify_ballot(signature, payload, public_key)
print(f"Signature valid: {is_valid}")  # Should be True
```

## Notes

- **Private key KHÔNG BAO GIỜ expose qua API**
- **Public key có thể public** (dùng để verify)
- **Signature không thể tạo lại** (mỗi phiếu chỉ sign 1 lần)
- **Keys không thể regenerate** sau khi đã tạo (để đảm bảo tính toàn vẹn)
