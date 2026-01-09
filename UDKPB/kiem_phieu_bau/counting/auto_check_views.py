"""
Views cho tính năng tự động kiểm phiếu
"""
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from poll.models import Poll
from .models import AIModelResult
from .auto_check_scheduler import start_scheduler, stop_scheduler, get_scheduler
import logging

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def toggle_auto_check(request, poll_id):
	"""
	Bật/tắt tự động kiểm phiếu cho poll
	KHÔNG tự động khởi động/dừng scheduler nữa
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
	
	logger.info(f"[AUTO CHECK] Poll {poll_id}: Auto check {'enabled' if auto_check_enabled else 'disabled'}")
	
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


@require_http_methods(["GET"])
def get_scheduler_status(request):
	"""
	Lấy trạng thái scheduler
	"""
	scheduler = get_scheduler()
	
	is_running = scheduler is not None and scheduler.running
	interval = scheduler.interval if scheduler else 15
	active_polls_count = AIModelResult.objects.filter(auto_check_enabled=True).count()
	
	return JsonResponse({
		'success': True,
		'scheduler_running': is_running,
		'interval': interval,
		'active_polls': active_polls_count,
		'message': f"Scheduler {'đang chạy' if is_running else 'đã dừng'} (interval: {interval}s, {active_polls_count} poll active)"
	})


@require_http_methods(["POST"])
def control_scheduler(request):
	"""
	Khởi động hoặc dừng scheduler thủ công
	"""
	action = request.POST.get('action')  # 'start' hoặc 'stop'
	
	if action == 'start':
		# Kiểm tra xem có poll nào bật auto check không
		active_polls = AIModelResult.objects.filter(auto_check_enabled=True).count()
		
		if active_polls == 0:
			return JsonResponse({
				'success': False,
				'error': 'Không có poll nào bật tự động kiểm phiếu',
				'message': 'Vui lòng bật "Tự động kiểm phiếu" cho ít nhất 1 poll trước'
			}, status=400)
		
		# Khởi động scheduler
		scheduler = get_scheduler()
		if scheduler and scheduler.running:
			return JsonResponse({
				'success': False,
				'error': 'Scheduler đã đang chạy',
				'message': 'Scheduler hiện đang hoạt động'
			}, status=400)
		
		logger.info(f"[SCHEDULER CONTROL] Starting scheduler manually...")
		start_scheduler(interval=15)
		logger.info(f"[SCHEDULER CONTROL] Scheduler started successfully")
		
		return JsonResponse({
			'success': True,
			'scheduler_running': True,
			'message': f'Đã khởi động scheduler thành công! Đang quét {active_polls} poll.'
		})
	
	elif action == 'stop':
		# Dừng scheduler
		scheduler = get_scheduler()
		if not scheduler or not scheduler.running:
			return JsonResponse({
				'success': False,
				'error': 'Scheduler chưa chạy',
				'message': 'Scheduler hiện không hoạt động'
			}, status=400)
		
		logger.info(f"[SCHEDULER CONTROL] Stopping scheduler manually...")
		stop_scheduler()
		logger.info(f"[SCHEDULER CONTROL] Scheduler stopped successfully")
		
		return JsonResponse({
			'success': True,
			'scheduler_running': False,
			'message': 'Đã dừng scheduler thành công!'
		})
	
	else:
		return JsonResponse({
			'success': False,
			'error': 'Invalid action',
			'message': 'Action phải là "start" hoặc "stop"'
		}, status=400)
