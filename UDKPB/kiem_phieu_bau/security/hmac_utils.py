"""
HMAC Utilities - Tiện ích HMAC cho xác thực QR Code phiếu bầu

Module này cung cấp các chức năng mã hóa cho:
- Tạo và quản lý HMAC secret keys
- Tạo chữ ký HMAC cho phiếu bầu
- Xác minh tính xác thực của phiếu bầu bằng HMAC
- Mã hóa/giải mã secret keys trước khi lưu vào database

Mô hình bảo mật:
1. Mỗi Poll có một HMAC secret key duy nhất (được mã hóa trong DB)
2. Mỗi Ballot nhận một chữ ký HMAC: HMAC(secret_key, ballot_data)
3. QR code chứa: {marker_id: 0, ballot_id: X, hmac: "..."}
4. Xác minh: Tính lại HMAC và so sánh với giá trị trong QR code
"""

import hmac
import hashlib
import secrets
import base64
from cryptography.fernet import Fernet
from django.conf import settings
from typing import Optional, Dict, Any
from datetime import datetime


class HMACKeyError(Exception):
    """Exception được raise khi có lỗi liên quan đến HMAC key"""
    pass


def get_encryption_key() -> bytes:
    """
    Lấy master encryption key từ Django settings.
    Được sử dụng để mã hóa/giải mã HMAC secret keys trước khi lưu vào database.
    
    Returns:
        bytes: 32-byte encryption key được tạo từ Django SECRET_KEY
    
    Raises:
        HMACKeyError: Nếu SECRET_KEY không được cấu hình hoặc quá ngắn
    """
    try:
        secret_key = settings.SECRET_KEY
        if len(secret_key) < 32:
            raise HMACKeyError("Django SECRET_KEY must be at least 32 characters")
        
        # Sử dụng 32 ký tự đầu của SECRET_KEY và encode thành bytes
        key_material = secret_key[:32].encode('utf-8')
        # Fernet yêu cầu 32-byte key được encode base64
        return base64.urlsafe_b64encode(key_material.ljust(32)[:32])
    except AttributeError:
        raise HMACKeyError("Django SECRET_KEY not configured in settings")


def generate_hmac_secret_key() -> str:
    """
    Tạo một HMAC secret key ngẫu nhiên an toàn về mặt mã hóa.
    
    Returns:
        str: Chuỗi hexadecimal 64 ký tự (256 bits entropy)
    
    Example:
        >>> key = generate_hmac_secret_key()
        >>> len(key)
        64
    """
    return secrets.token_hex(32)  # 32 bytes = 256 bits = 64 hex chars


def encrypt_hmac_key(hmac_key: str) -> str:
    """
    Mã hóa HMAC secret key trước khi lưu vào database.
    Sử dụng Fernet symmetric encryption với master key từ settings.
    
    Args:
        hmac_key (str): HMAC secret key dạng plain text (hex string)
    
    Returns:
        str: Encrypted key được encode base64 (an toàn để lưu vào database)
    
    Raises:
        HMACKeyError: Nếu mã hóa thất bại
    
    Example:
        >>> plain_key = generate_hmac_secret_key()
        >>> encrypted = encrypt_hmac_key(plain_key)
        >>> # Lưu encrypted vào database
    """
    try:
        encryption_key = get_encryption_key()
        fernet = Fernet(encryption_key)
        
        # Mã hóa HMAC key
        encrypted_bytes = fernet.encrypt(hmac_key.encode('utf-8'))
        
        # Trả về dạng base64 string để lưu vào database
        return base64.b64encode(encrypted_bytes).decode('utf-8')
    except Exception as e:
        raise HMACKeyError(f"Failed to encrypt HMAC key: {str(e)}")


def decrypt_hmac_key(encrypted_key: str) -> str:
    """
    Giải mã HMAC secret key lấy từ database.
    
    Args:
        encrypted_key (str): Encrypted key được encode base64 từ database
    
    Returns:
        str: HMAC secret key dạng plain text (hex string)
    
    Raises:
        HMACKeyError: Nếu giải mã thất bại (sai key, dữ liệu bị hỏng, v.v.)
    
    Example:
        >>> encrypted = poll.hmac_secret_key  # Từ database
        >>> plain_key = decrypt_hmac_key(encrypted)
        >>> # Dùng plain_key để tạo/verify HMAC
    """
    try:
        encryption_key = get_encryption_key()
        fernet = Fernet(encryption_key)
        
        # Decode từ base64
        encrypted_bytes = base64.b64decode(encrypted_key.encode('utf-8'))
        
        # Giải mã
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        raise HMACKeyError(f"Failed to decrypt HMAC key: {str(e)}")


def create_ballot_hmac(
    ballot_id: int,
    poll_id: int,
    hmac_secret_key: str,
    timestamp: Optional[datetime] = None,
    length: int = 12
) -> str:
    """
    Tạo chữ ký HMAC cho phiếu bầu.
    
    Args:
        ballot_id (int): Mã định danh phiếu bầu (duy nhất)
        poll_id (int): Mã định danh cuộc bỏ phiếu (để tăng cường bảo mật)
        hmac_secret_key (str): HMAC secret key dạng plain text (hex string)
        timestamp (datetime, optional): Thời gian tạo phiếu bầu. Mặc định None.
        length (int, optional): Độ dài output HMAC (số ký tự hex). Mặc định 12.
    
    Returns:
        str: Chữ ký HMAC (hex string, cắt ngắn theo độ dài chỉ định)
    
    Example:
        >>> # Lấy plain key từ database
        >>> plain_key = decrypt_hmac_key(poll.hmac_secret_key)
        >>> # Tạo HMAC cho ballot
        >>> hmac_sig = create_ballot_hmac(
        ...     ballot_id=123,
        ...     poll_id=456,
        ...     hmac_secret_key=plain_key,
        ...     length=12
        ... )
        >>> print(hmac_sig)  # "a3f8e92bd4c1"
    """
    # Xây dựng message để ký
    message_parts = [str(ballot_id), str(poll_id)]
    
    if timestamp:
        # Thêm timestamp để xác minh dựa trên thời gian
        timestamp_str = timestamp.strftime('%Y%m%d%H%M%S')
        message_parts.append(timestamp_str)
    
    message = ':'.join(message_parts)
    
    # Tạo HMAC-SHA256
    hmac_hash = hmac.new(
        hmac_secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Trả về hex string đã cắt ngắn
    return hmac_hash[:length]


def verify_ballot_hmac(
    ballot_id: int,
    poll_id: int,
    hmac_signature: str,
    hmac_secret_key: str,
    timestamp: Optional[datetime] = None
) -> bool:
    """
    Xác minh chữ ký HMAC của phiếu bầu.
    
    Args:
        ballot_id (int): Mã phiếu bầu từ QR code
        poll_id (int): Mã cuộc bỏ phiếu
        hmac_signature (str): Chữ ký HMAC từ QR code
        hmac_secret_key (str): HMAC secret key dạng plain text (hex string)
        timestamp (datetime, optional): Thời gian tạo phiếu bầu. Mặc định None.
    
    Returns:
        bool: True nếu chữ ký hợp lệ, False nếu không hợp lệ
    
    Example:
        >>> # Đọc dữ liệu QR code
        >>> qr_data = {"marker_id": 0, "ballot_id": 123, "hmac": "a3f8e92bd4c1"}
        >>> # Lấy ballot từ database
        >>> ballot = Ballot.objects.get(ballot_id=qr_data["ballot_id"])
        >>> # Lấy plain key
        >>> plain_key = decrypt_hmac_key(ballot.poll.hmac_secret_key)
        >>> # Xác minh
        >>> is_valid = verify_ballot_hmac(
        ...     ballot_id=ballot.ballot_id,
        ...     poll_id=ballot.poll.poll_id,
        ...     hmac_signature=qr_data["hmac"],
        ...     hmac_secret_key=plain_key,
        ...     timestamp=ballot.timestamp
        ... )
        >>> if is_valid:
        ...     print("✓ Phiếu bầu xác thực")
        ... else:
        ...     print("✗ Phiếu bầu giả mạo hoặc bị thay đổi")
    """
    # Tính lại HMAC kỳ vọng
    expected_hmac = create_ballot_hmac(
        ballot_id=ballot_id,
        poll_id=poll_id,
        hmac_secret_key=hmac_secret_key,
        timestamp=timestamp,
        length=len(hmac_signature)  # Khớp độ dài với chữ ký được cung cấp
    )
    
    # Sử dụng so sánh constant-time để ngăn chặn timing attacks
    return hmac.compare_digest(expected_hmac, hmac_signature)


def generate_qr_data(ballot_id: int, hmac_signature: str, marker_id: int = 0) -> str:
    """
    Tạo cấu trúc dữ liệu QR code để xác minh phiếu bầu.
    Format đơn giản: "marker_id:ballot_id:hmac"
    
    Args:
        ballot_id (int): Mã định danh phiếu bầu
        hmac_signature (str): Chữ ký HMAC
        marker_id (int, optional): ID của ArUco marker. Mặc định 0.
    
    Returns:
        str: Chuỗi QR data format "marker_id:ballot_id:hmac"
    
    Example:
        >>> hmac_sig = create_ballot_hmac(123, 456, secret_key)
        >>> qr_data = generate_qr_data(ballot_id=123, hmac_signature=hmac_sig)
        >>> print(qr_data)
        "0:123:a3f8e92bd4c1"
    """
    return f"{marker_id}:{ballot_id}:{hmac_signature}"


def initialize_poll_hmac_key(poll) -> str:
    """
    Khởi tạo HMAC secret key cho một poll mới.
    Tạo, mã hóa và lưu key vào poll model.
    
    Args:
        poll: Poll model instance (đã lưu hoặc chưa lưu)
    
    Returns:
        str: HMAC secret key dạng plain text (để sử dụng ngay, không lưu trữ!)
    
    Example:
        >>> from poll.models import Poll
        >>> poll = Poll.objects.create(title="Bầu cử 2024")
        >>> plain_key = initialize_poll_hmac_key(poll)
        >>> # poll.hmac_secret_key đã được mã hóa và lưu
        >>> # Dùng plain_key để tạo ballot HMACs ngay lập tức
    """
    from django.utils import timezone
    
    # Tạo secret key mới
    plain_key = generate_hmac_secret_key()
    
    # Mã hóa trước khi lưu
    encrypted_key = encrypt_hmac_key(plain_key)
    
    # Lưu vào poll
    poll.hmac_secret_key = encrypted_key
    poll.key_generated_at = timezone.now()
    poll.save(update_fields=['hmac_secret_key', 'key_generated_at'])
    
    return plain_key


# Các hàm tiện ích cho workflow thông dụng

def create_ballot_with_hmac(ballot, save: bool = True) -> str:
    """
    Tạo chữ ký HMAC cho phiếu bầu và lưu trữ.
    
    Args:
        ballot: Ballot model instance
        save (bool, optional): Lưu ballot sau khi set HMAC. Mặc định True.
    
    Returns:
        str: Chữ ký HMAC (cũng được lưu vào ballot.qr_hmac)
    
    Raises:
        HMACKeyError: Nếu poll chưa có HMAC key được cấu hình
    
    Example:
        >>> from ballot.models import Ballot
        >>> ballot = Ballot(poll=poll, ballot_id=123)
        >>> hmac_sig = create_ballot_with_hmac(ballot)
        >>> print(ballot.qr_hmac)  # "a3f8e92bd4c1"
    """
    from django.utils import timezone
    
    if not ballot.poll.hmac_secret_key:
        raise HMACKeyError(f"Poll {ballot.poll.poll_id} doesn't have HMAC key configured")
    
    # Giải mã key
    plain_key = decrypt_hmac_key(ballot.poll.hmac_secret_key)
    
    # Tạo HMAC
    hmac_sig = create_ballot_hmac(
        ballot_id=ballot.ballot_id,
        poll_id=ballot.poll.poll_id,
        hmac_secret_key=plain_key,
        timestamp=ballot.timestamp
    )
    
    # Lưu vào ballot
    ballot.qr_hmac = hmac_sig
    ballot.qr_generated_at = timezone.now()
    
    if save:
        ballot.save(update_fields=['qr_hmac', 'qr_generated_at'])
    
    return hmac_sig


def verify_ballot_from_qr(ballot, qr_hmac: str) -> bool:
    """
    Xác minh phiếu bầu sử dụng HMAC từ QR code đã quét.
    
    Args:
        ballot: Ballot model instance từ database
        qr_hmac (str): Chữ ký HMAC từ QR code đã quét
    
    Returns:
        bool: True nếu phiếu bầu xác thực, False nếu không
    
    Example:
        >>> # Quét QR code
        >>> qr_data = scan_qr_code(image)
        >>> ballot_id = qr_data["ballot_id"]
        >>> qr_hmac = qr_data["hmac"]
        >>> # Lấy ballot từ DB
        >>> ballot = Ballot.objects.get(ballot_id=ballot_id)
        >>> # Xác minh
        >>> if verify_ballot_from_qr(ballot, qr_hmac):
        ...     print("✓ Phiếu bầu xác thực")
        ... else:
        ...     print("✗ Phiếu bầu giả mạo")
    """
    try:
        # Giải mã key
        plain_key = decrypt_hmac_key(ballot.poll.hmac_secret_key)
        
        # Xác minh
        return verify_ballot_hmac(
            ballot_id=ballot.ballot_id,
            poll_id=ballot.poll.poll_id,
            hmac_signature=qr_hmac,
            hmac_secret_key=plain_key,
            timestamp=ballot.timestamp
        )
    except Exception:
        return False
