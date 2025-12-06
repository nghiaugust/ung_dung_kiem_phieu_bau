"""
Security Views - API endpoints cho các thao tác mã hóa
Cung cấp các endpoint để tạo key, sign và verify phiếu bầu qua QR code
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from poll.models import Poll
from ballot.models import Ballot
from .crypto_utils import CryptoService, generate_keys, sign_ballot, verify_ballot
import json


# =====================================================
# API QUẢN LÝ MÃ HÓA (CRYPTOGRAPHIC MANAGEMENT APIs)
# =====================================================


@csrf_exempt
@require_http_methods(["POST"])
def verify_ballot_qr(request):
    """
    Xác thực chữ ký QR của phiếu bầu (Public endpoint cho mobile app)
    Endpoint này không cần đăng nhập, dùng để verify phiếu khi scan QR
    
    POST /security/ballot/verify/
    Body: {
        "poll_id": 1,
        "ballot_id": 123,
        "signature": "base64_signature..."
    }
    
    Response:
    {
        "success": true,
        "valid": true,
        "message": "Phiếu hợp lệ",
        "ballot": {
            "ballot_id": 123,
            "poll_id": 1,
            "poll_title": "Bầu cử 2025",
            "is_valid": true,
            "qr_payload": {...}
        },
        "poll": {
            "public_key": "base64_public_key...",
            "title": "Bầu cử 2025"
        }
    }
    """
    try:
        # Parse dữ liệu từ request body
        data = json.loads(request.body)
        poll_id = data.get('poll_id')
        ballot_id = data.get('ballot_id')
        signature_b64 = data.get('signature')
        
        # Validate dữ liệu đầu vào
        if not all([poll_id, ballot_id, signature_b64]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields',
                'message': 'Thiếu thông tin: poll_id, ballot_id, hoặc signature'
            }, status=400)
        
        # Lấy thông tin phiếu bầu từ database
        try:
            ballot = Ballot.objects.select_related('poll').get(
                ballot_id=ballot_id,
                poll_id=poll_id
            )
        except Ballot.DoesNotExist:
            return JsonResponse({
                'success': False,
                'valid': False,
                'error': 'Ballot not found',
                'message': 'Phiếu không tồn tại trong hệ thống'
            }, status=404)
        
        poll = ballot.poll
        
        # Kiểm tra xem phiếu đã có QR signature chưa
        if not ballot.qr_signature or not ballot.qr_payload:
            return JsonResponse({
                'success': False,
                'valid': False,
                'error': 'No QR signature',
                'message': 'Phiếu chưa được cấp mã QR'
            }, status=400)
        
        # Bước 1: So sánh signature với database (kiểm tra nhanh)
        if ballot.qr_signature != signature_b64:
            return JsonResponse({
                'success': True,
                'valid': False,
                'message': 'Chữ ký không khớp - Phiếu có thể bị giả mạo',
                'ballot': {
                    'ballot_id': ballot.ballot_id,
                    'poll_id': ballot.poll_id
                }
            }, status=200)
        
        # Kiểm tra xem poll có public key không
        if not poll.public_key:
            return JsonResponse({
                'success': False,
                'error': 'No public key',
                'message': 'Cuộc bỏ phiếu chưa được cấu hình mã hóa'
            }, status=400)
        
        # Bước 2: Verify signature bằng RSA (xác thực mật mã học)
        is_valid = verify_ballot(signature_b64, ballot.qr_payload, poll.public_key)
        
        if not is_valid:
            return JsonResponse({
                'success': True,
                'valid': False,
                'message': 'Chữ ký không hợp lệ - Phiếu bị giả mạo',
                'ballot': {
                    'ballot_id': ballot.ballot_id,
                    'poll_id': ballot.poll_id
                }
            }, status=200)
        
        # Signature hợp lệ - Trả về thông tin phiếu
        return JsonResponse({
            'success': True,
            'valid': True,
            'message': 'Phiếu hợp lệ',
            'ballot': {
                'ballot_id': ballot.ballot_id,
                'poll_id': ballot.poll_id,
                'poll_title': poll.title,
                'is_valid': ballot.is_valid,
                'is_checked': ballot.is_checked,
                'qr_payload': ballot.qr_payload,
                'qr_generated_at': ballot.qr_generated_at.isoformat() if ballot.qr_generated_at else None
            },
            'poll': {
                'public_key': poll.public_key,
                'title': poll.title,
                'status': poll.status
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'message': 'Dữ liệu JSON không hợp lệ'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'message': 'Lỗi khi xác thực phiếu'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_poll_public_key(request, poll_id):
    """
    Lấy public key của cuộc bỏ phiếu (Public endpoint)
    Endpoint này không cần đăng nhập, dùng để mobile app lấy public key để verify
    
    GET /security/poll/<poll_id>/public-key/
    
    Response:
    {
        "success": true,
        "poll_id": 1,
        "public_key": "base64_public_key...",
        "key_generated_at": "2025-12-05T10:30:00Z"
    }
    """
    try:
        # Lấy thông tin cuộc bỏ phiếu
        poll = get_object_or_404(Poll, poll_id=poll_id)
        
        # Kiểm tra xem đã có public key chưa
        if not poll.public_key:
            return JsonResponse({
                'success': False,
                'error': 'No public key',
                'message': 'Cuộc bỏ phiếu chưa có public key'
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'poll_id': poll.poll_id,
            'poll_title': poll.title,
            'public_key': poll.public_key,
            'key_generated_at': poll.key_generated_at.isoformat() if poll.key_generated_at else None
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
