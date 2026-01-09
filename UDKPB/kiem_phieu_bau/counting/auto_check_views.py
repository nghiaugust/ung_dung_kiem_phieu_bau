"""
Views cho tính năng tự động kiểm phiếu
"""
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from poll.models import Poll
from .models import AIModelResult


@require_http_methods(["POST"])
def toggle_auto_check(request, poll_id):
	"""
	Bật/tắt tự động kiểm phiếu cho poll
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	# Lấy AIModelResult gần nhất
	ai_result = AIModelResult.objects.filter(poll=poll).order_by('-created_at').first()
	
	if not ai_result:
		return JsonResponse({
			'success': False,
			'error': 'Chưa có cấu hình kiểm phiếu. Vui lòng lưu cấu hình kiểm phiếu trước.'
		}, status=400)
	
	# Lấy giá trị từ request
	auto_check_enabled = request.POST.get('auto_check_enabled') == 'true'
	auto_check_max_ballots_str = request.POST.get('auto_check_max_ballots', '').strip()
	auto_check_max_ballots = int(auto_check_max_ballots_str) if auto_check_max_ballots_str else None
	
	# Cập nhật
	ai_result.auto_check_enabled = auto_check_enabled
	ai_result.auto_check_max_ballots = auto_check_max_ballots
	ai_result.save()
	
	return JsonResponse({
		'success': True,
		'auto_check_enabled': ai_result.auto_check_enabled,
		'auto_check_max_ballots': ai_result.auto_check_max_ballots,
		'auto_check_processed': ai_result.auto_check_processed,
		'message': f"Đã {'bật' if auto_check_enabled else 'tắt'} tự động kiểm phiếu"
	})


@require_http_methods(["GET"])
def get_auto_check_status(request, poll_id):
	"""
	Lấy trạng thái tự động kiểm phiếu
	"""
	poll = get_object_or_404(Poll, poll_id=poll_id)
	
	ai_result = AIModelResult.objects.filter(poll=poll).order_by('-created_at').first()
	
	if not ai_result:
		return JsonResponse({
			'success': False,
			'auto_check_enabled': False,
			'auto_check_max_ballots': None,
			'auto_check_processed': 0
		})
	
	return JsonResponse({
		'success': True,
		'auto_check_enabled': ai_result.auto_check_enabled,
		'auto_check_max_ballots': ai_result.auto_check_max_ballots,
		'auto_check_processed': ai_result.auto_check_processed,
		'config_type': ai_result.result_model.get('config', {}).get('type', 'unknown')
	})
