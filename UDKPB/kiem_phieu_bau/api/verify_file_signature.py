"""
Xác thực chữ ký số của file bằng RSA với SHA256
"""
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


def verify_file_signature(public_key_pem: str, signature_base64: str, file_data: bytes) -> dict:
    """
    Xác thực chữ ký số của file
    
    Args:
        public_key_pem: Public key dạng PEM string
        signature_base64: Chữ ký đã mã hóa base64
        file_data: Dữ liệu file gốc (bytes)
    
    Returns:
        dict: {
            'verified': bool,
            'error': str (nếu có lỗi)
        }
    """
    try:
        # Kiểm tra input
        if not public_key_pem:
            return {
                'verified': False,
                'error': 'Public key không được cung cấp'
            }
        
        if not signature_base64:
            return {
                'verified': False,
                'error': 'Chữ ký không được cung cấp'
            }
        
        if not file_data:
            return {
                'verified': False,
                'error': 'Dữ liệu file trống'
            }
        
        # Load public key từ PEM string
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
        except Exception as e:
            return {
                'verified': False,
                'error': f'Không thể load public key: {str(e)}'
            }
        
        # Decode signature từ base64
        try:
            signature = base64.b64decode(signature_base64)
        except Exception as e:
            return {
                'verified': False,
                'error': f'Không thể decode chữ ký base64: {str(e)}'
            }
        
        # Verify signature với RSA-PSS và SHA256
        try:
            public_key.verify(
                signature,
                file_data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Nếu không có exception nghĩa là verify thành công
            return {
                'verified': True,
                'error': None
            }
            
        except InvalidSignature:
            return {
                'verified': False,
                'error': 'Chữ ký không hợp lệ - file có thể đã bị chỉnh sửa'
            }
        except Exception as e:
            return {
                'verified': False,
                'error': f'Lỗi khi verify chữ ký: {str(e)}'
            }
    
    except Exception as e:
        return {
            'verified': False,
            'error': f'Lỗi không xác định: {str(e)}'
        }


def verify_multiple_files(public_key_pem: str, signatures: dict, files_data: dict) -> dict:
    """
    Xác thực chữ ký của nhiều file cùng lúc
    
    Args:
        public_key_pem: Public key dạng PEM string
        signatures: Dict {filename: signature_base64}
        files_data: Dict {filename: file_bytes}
    
    Returns:
        dict: {
            'all_verified': bool,
            'results': {filename: verify_result},
            'failed_files': [filename1, filename2, ...]
        }
    """
    results = {}
    failed_files = []
    
    for filename, file_data in files_data.items():
        signature = signatures.get(filename)
        
        if not signature:
            results[filename] = {
                'verified': False,
                'error': 'Không tìm thấy chữ ký cho file này'
            }
            failed_files.append(filename)
            continue
        
        # Verify từng file
        verify_result = verify_file_signature(public_key_pem, signature, file_data)
        results[filename] = verify_result
        
        if not verify_result['verified']:
            failed_files.append(filename)
    
    return {
        'all_verified': len(failed_files) == 0,
        'results': results,
        'failed_files': failed_files
    }
