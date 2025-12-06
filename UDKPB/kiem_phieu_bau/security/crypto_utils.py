"""
Tiện ích Mã hóa cho Xác thực QR Code Phiếu Bầu
Sử dụng RSA Digital Signature (2048-bit) để ký và xác thực mã QR trên phiếu bầu
"""

import base64
import json
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


class CryptoService:
    """
    Lớp service cho các thao tác mã hóa sử dụng RSA Digital Signature
    """
    
    # Kích thước RSA key (2048 bits là mức tối thiểu được khuyến nghị cho bảo mật)
    KEY_SIZE = 2048
    
    # Public exponent (giá trị chuẩn)
    PUBLIC_EXPONENT = 65537
    
    @staticmethod
    def generate_key_pair():
        """
        Tạo cặp RSA key pair (private key + public key)
        
        Returns:
            tuple: (private_key_b64, public_key_b64)
                - private_key_b64: Private key được mã hóa Base64 (định dạng PEM)
                - public_key_b64: Public key được mã hóa Base64 (định dạng PEM)
        """
        # Tạo private key
        private_key = rsa.generate_private_key(
            public_exponent=CryptoService.PUBLIC_EXPONENT,
            key_size=CryptoService.KEY_SIZE,
            backend=default_backend()
        )
        
        # Chuyển private key sang định dạng PEM
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()  # Không bảo vệ bằng mật khẩu
        )
        
        # Lấy public key từ private key
        public_key = private_key.public_key()
        
        # Chuyển public key sang định dạng PEM
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Mã hóa Base64 để lưu trữ trong database
        private_key_b64 = base64.b64encode(private_pem).decode('utf-8')
        public_key_b64 = base64.b64encode(public_pem).decode('utf-8')
        
        return private_key_b64, public_key_b64
    
    @staticmethod
    def sign_payload(payload_dict, private_key_b64):
        """
        Ký một payload bằng RSA private key
        
        Args:
            payload_dict (dict): Payload cần ký (sẽ được serialize thành JSON)
            private_key_b64 (str): Private key đã mã hóa Base64
            
        Returns:
            str: Chữ ký (signature) đã mã hóa Base64
            
        Example:
            payload = {
                "poll_id": 1,
                "ballot_id": 123,
                "timestamp": "2025-12-05T10:30:00Z",
                "salt": "random_string"
            }
            signature = CryptoService.sign_payload(payload, private_key)
        """
        # Serialize payload thành canonical JSON (keys được sắp xếp để đảm bảo output nhất quán)
        payload_str = CryptoService._serialize_payload(payload_dict)
        payload_bytes = payload_str.encode('utf-8')
        
        # Giải mã private key từ Base64
        private_pem = base64.b64decode(private_key_b64)
        
        # Load private key
        private_key = serialization.load_pem_private_key(
            private_pem,
            password=None,
            backend=default_backend()
        )
        
        # Ký payload sử dụng PSS padding (an toàn hơn PKCS1v15)
        signature = private_key.sign(
            payload_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        # Mã hóa signature thành Base64
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return signature_b64
    
    @staticmethod
    def verify_signature(payload_dict, signature_b64, public_key_b64):
        """
        Xác thực chữ ký bằng RSA public key
        
        Args:
            payload_dict (dict): Payload đã được ký
            signature_b64 (str): Chữ ký đã mã hóa Base64
            public_key_b64 (str): Public key đã mã hóa Base64
            
        Returns:
            bool: True nếu chữ ký hợp lệ, False nếu không hợp lệ
            
        Example:
            is_valid = CryptoService.verify_signature(payload, signature, public_key)
        """
        try:
            # Serialize payload thành canonical JSON (giống như khi ký)
            payload_str = CryptoService._serialize_payload(payload_dict)
            payload_bytes = payload_str.encode('utf-8')
            
            # Giải mã signature và public key từ Base64
            signature = base64.b64decode(signature_b64)
            public_pem = base64.b64decode(public_key_b64)
            
            # Load public key
            public_key = serialization.load_pem_public_key(
                public_pem,
                backend=default_backend()
            )
            
            # Xác thực chữ ký
            public_key.verify(
                signature,
                payload_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Nếu không có exception, chữ ký hợp lệ
            return True
            
        except InvalidSignature:
            # Xác thực chữ ký thất bại
            return False
        except Exception as e:
            # Các lỗi khác (key bị lỗi, etc.)
            print(f"Lỗi xác thực: {e}")
            return False
    
    @staticmethod
    def _serialize_payload(payload_dict):
        """
        Serialize payload thành chuỗi JSON chuẩn (deterministic)
        Keys được sắp xếp theo thứ tự alphabet để đảm bảo output giống nhau mỗi lần
        
        Args:
            payload_dict (dict): Dictionary payload
            
        Returns:
            str: Chuỗi JSON với keys đã được sắp xếp
        """
        return json.dumps(payload_dict, sort_keys=True, separators=(',', ':'))
    
    @staticmethod
    def generate_ballot_payload(poll_id, ballot_id, salt=None):
        """
        Tạo payload chuẩn cho phiếu bầu (dùng cho QR code)
        
        Args:
            poll_id (int): ID cuộc bỏ phiếu
            ballot_id (int): ID phiếu bầu
            salt (str, optional): Salt ngẫu nhiên để tạo tính duy nhất. Tự động tạo nếu không cung cấp.
            
        Returns:
            dict: Dictionary payload
        """
        import secrets
        
        if salt is None:
            # Tạo salt ngẫu nhiên (16 bytes = 32 ký tự hex)
            salt = secrets.token_hex(16)
        
        payload = {
            "poll_id": poll_id,
            "ballot_id": ballot_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "salt": salt
        }
        
        return payload
    
    @staticmethod
    def generate_qr_data(signature_b64, poll_id, ballot_id):
        """
        Tạo dữ liệu QR code ở định dạng compact (tối giản)
        
        Args:
            signature_b64 (str): Chữ ký đã mã hóa Base64
            poll_id (int): ID cuộc bỏ phiếu
            ballot_id (int): ID phiếu bầu
            
        Returns:
            str: Chuỗi JSON cho QR code
        """
        qr_data = {
            "s": signature_b64,  # signature (chữ ký)
            "p": poll_id,        # poll_id (ID cuộc bỏ phiếu)
            "b": ballot_id       # ballot_id (ID phiếu bầu)
        }
        
        return json.dumps(qr_data, separators=(',', ':'))
    
    @staticmethod
    def parse_qr_data(qr_json_str):
        """
        Parse (phân tích) dữ liệu từ QR code
        
        Args:
            qr_json_str (str): Chuỗi JSON từ QR code
            
        Returns:
            dict: Dữ liệu đã parse với keys: signature, poll_id, ballot_id
        """
        qr_data = json.loads(qr_json_str)
        
        return {
            "signature": qr_data.get("s"),
            "poll_id": qr_data.get("p"),
            "ballot_id": qr_data.get("b")
        }


# =====================================================
# CÁC HÀM TIỆN ÍCH (Wrappers cho các thao tác thường dùng)
# =====================================================

def generate_keys():
    """
    Hàm tiện ích để tạo cặp RSA key pair
    
    Returns: 
        tuple: (private_key_b64, public_key_b64)
    """
    return CryptoService.generate_key_pair()


def sign_ballot(poll_id, ballot_id, private_key_b64, salt=None):
    """
    Hàm tiện ích để ký một phiếu bầu
    
    Args:
        poll_id (int): ID cuộc bỏ phiếu
        ballot_id (int): ID phiếu bầu
        private_key_b64 (str): Private key đã mã hóa Base64
        salt (str, optional): Salt ngẫu nhiên
        
    Returns:
        tuple: (signature_b64, payload_dict, qr_json_str)
            - signature_b64: Chữ ký đã mã hóa Base64
            - payload_dict: Payload gốc (để lưu vào DB)
            - qr_json_str: Chuỗi JSON cho QR code
    """
    # Tạo payload
    payload = CryptoService.generate_ballot_payload(poll_id, ballot_id, salt)
    
    # Ký payload
    signature = CryptoService.sign_payload(payload, private_key_b64)
    
    # Tạo dữ liệu QR code
    qr_data = CryptoService.generate_qr_data(signature, poll_id, ballot_id)
    
    return signature, payload, qr_data


def verify_ballot(signature_b64, payload_dict, public_key_b64):
    """
    Hàm tiện ích để xác thực chữ ký của phiếu bầu
    
    Args:
        signature_b64 (str): Chữ ký đã mã hóa Base64
        payload_dict (dict): Payload gốc
        public_key_b64 (str): Public key đã mã hóa Base64
        
    Returns:
        bool: True nếu hợp lệ, False nếu không hợp lệ
    """
    return CryptoService.verify_signature(payload_dict, signature_b64, public_key_b64)
