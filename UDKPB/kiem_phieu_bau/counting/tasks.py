"""
Celery tasks cho kiểm phiếu tự động
"""
import os
import gc
import time
import requests
from typing import Dict, List, Tuple
from django.conf import settings
from celery import shared_task

from ballot.models import Ballot
from poll.models import Poll
from preprocessing.models import BallotCell
from counting.models import AIModelResult
from counting import config_model
from counting.configurations.base import (
    MODEL_RESNET18_CROSSED,
    MODEL_RESNET18_X,
    MODEL_VIETNAMEOCR,
)
from config.service_manager import get_model_api_url


def prepare_batch_requests(ballot, ai_result, all_cell_models):
    """
    Chuẩn bị và gom các ảnh theo model thành batch để gửi request
    
    Args:
        ballot: Ballot object
        ai_result: AIModelResult object
        all_cell_models: Dict mapping cell_key -> model_name
        
    Returns:
        Tuple[Dict, Dict, Dict]: (vietnameocr_batch, resnet18_x_batch, resnet18_crossed_batch)
    """
    vietnameocr_batch = {'image_paths': [], 'cell_mapping': {}}
    resnet18_x_batch = {'image_paths': [], 'cell_mapping': {}}
    resnet18_crossed_batch = {'image_paths': [], 'cell_mapping': {}}
    
    # QUAN TRỌNG: Sort cells theo thứ tự (row, col) để đảm bảo thứ tự ổn định
    sorted_cells = sorted(all_cell_models.items(), key=lambda x: tuple(map(int, x[0].split('_'))))
    
    # Gom ảnh theo model
    for cell_key, model_name in sorted_cells:
        # Parse cell_key: "row_col"
        row, col = map(int, cell_key.split('_'))
        
        # Lấy BallotCell tương ứng
        ballot_cells = BallotCell.objects.filter(
            preprocessed_ballot__ballot=ballot,
            row=row,
            col=col
        ).select_related('preprocessed_ballot')
        
        if not ballot_cells.exists():
            continue
        
        ballot_cell = ballot_cells.first()
        cell_image_path = os.path.join(settings.MEDIA_ROOT, ballot_cell.cell_image)
        
        if not os.path.exists(cell_image_path):
            continue
        
        # Gom vào batch tương ứng
        if model_name == MODEL_VIETNAMEOCR:
            idx = len(vietnameocr_batch['image_paths'])
            vietnameocr_batch['image_paths'].append(cell_image_path)
            vietnameocr_batch['cell_mapping'][idx] = (row, col)
        elif model_name == MODEL_RESNET18_X:
            idx = len(resnet18_x_batch['image_paths'])
            resnet18_x_batch['image_paths'].append(cell_image_path)
            resnet18_x_batch['cell_mapping'][idx] = (row, col)
        elif model_name == MODEL_RESNET18_CROSSED:
            idx = len(resnet18_crossed_batch['image_paths'])
            resnet18_crossed_batch['image_paths'].append(cell_image_path)
            resnet18_crossed_batch['cell_mapping'][idx] = (row, col)
    
    return vietnameocr_batch, resnet18_x_batch, resnet18_crossed_batch


def process_batch_responses(
    ai_result,
    vietnameocr_batch,
    resnet18_x_batch,
    resnet18_crossed_batch,
    vietnameocr_response,
    resnet18_x_response,
    resnet18_crossed_response
):
    """
    Xử lý kết quả trả về từ API và lưu vào database
    
    Args:
        ai_result: AIModelResult object
        vietnameocr_batch: Dict chua thong tin batch VietNameOCR
        resnet18_x_batch: Dict chua thong tin batch model_resnet18_x
        resnet18_crossed_batch: Dict chua thong tin batch ResNet18 crossed
        
    Returns:
        int: Số lượng cells đã xử lý thành công
    """
    total_processed_cells = 0
    
    # Xu ly VietNameOCR response
    if vietnameocr_response and vietnameocr_response.get('success') and vietnameocr_response.get('results'):
        results = vietnameocr_response['results']
        for idx, result in enumerate(results):
            if idx in vietnameocr_batch['cell_mapping']:
                row, col = vietnameocr_batch['cell_mapping'][idx]
                recognized_text = result.get('text', '')
                confidence = result.get('confidence', 0)
                
                ai_result.set_cell_result(row, col, recognized_text, confidence)
                total_processed_cells += 1
    
    # Xu ly model_resnet18_x response
    if resnet18_x_response and resnet18_x_response.get('success') and resnet18_x_response.get('results'):
        results = resnet18_x_response['results']
        for idx, result in enumerate(results):
            if idx in resnet18_x_batch['cell_mapping']:
                row, col = resnet18_x_batch['cell_mapping'][idx]
                label = result.get('label', 'none')
                
                # Lấy confidence cao nhất
                confidence = result.get('confidence', 0)
                
                # Lưu kết quả (label + detections)
                result_data = {
                    'label': label,
                    'raw_label': result.get('raw_label', ''),
                    'is_marked': result.get('is_marked'),
                    'is_cancelled': result.get('is_cancelled'),
                    'probabilities': result.get('probabilities', {}),
                    'detections': result.get('detections', [])
                }
                ai_result.set_cell_result(row, col, result_data, confidence)
                total_processed_cells += 1
    
    # Xu ly model_resnet18_crossed response cho phieu gach ten.
    if resnet18_crossed_response and resnet18_crossed_response.get('success') and resnet18_crossed_response.get('results'):
        results = resnet18_crossed_response['results']
        for idx, result in enumerate(results):
            if idx in resnet18_crossed_batch['cell_mapping']:
                row, col = resnet18_crossed_batch['cell_mapping'][idx]
                result_data = {
                    'label': result.get('label', 'unknown'),
                    'raw_label': result.get('raw_label', ''),
                    'is_struck': result.get('is_struck'),
                    'probabilities': result.get('probabilities', {}),
                    'detections': result.get('detections', [])
                }
                confidence = result.get('confidence', 0)
                ai_result.set_cell_result(row, col, result_data, confidence)
                total_processed_cells += 1

    return total_processed_cells


def send_batch_request(api_url, image_paths, extra_data=None, timeout=300):
    """
    Gửi batch request tới AI API
    
    Args:
        api_url: URL của API
        image_paths: Danh sách đường dẫn ảnh
        extra_data: Dict chứa data bổ sung (optional)
        timeout: Timeout cho request (giây)
        
    Returns:
        Dict: Response từ API
        
    Raises:
        requests.exceptions.RequestException: Khi request thất bại
    """
    if not image_paths:
        return {'success': True, 'results': []}
    
    file_handles = []
    try:
        files = []
        for idx, path in enumerate(image_paths):
            # QUAN TRỌNG: Thêm index vào filename để đảm bảo có thể map lại đúng thứ tự
            # Format: {idx:04d}_{original_filename}
            original_filename = os.path.basename(path)
            indexed_filename = f"{idx:04d}_{original_filename}"
            fh = open(path, 'rb')
            file_handles.append(fh)
            files.append(('images', (indexed_filename, fh, 'image/jpeg')))
        
        # Gửi request
        response = requests.post(api_url, files=files, data=extra_data, timeout=timeout)
        response.raise_for_status()  # Raise exception nếu status code không phải 2xx
        
        result = response.json()
        
        # Giải phóng memory
        gc.collect()
        
        return result
        
    except requests.exceptions.Timeout as e:
        raise requests.exceptions.RequestException(f"Request timeout sau {timeout}s: {str(e)}")
    except requests.exceptions.ConnectionError as e:
        raise requests.exceptions.RequestException(f"Không thể kết nối tới AI server: {str(e)}")
    except requests.exceptions.HTTPError as e:
        raise requests.exceptions.RequestException(f"HTTP error {response.status_code}: {str(e)}")
    except Exception as e:
        raise requests.exceptions.RequestException(f"Lỗi không xác định: {str(e)}")
    finally:
        # Đảm bảo đóng tất cả file handles
        for fh in file_handles:
            try:
                fh.close()
            except:
                pass



@shared_task(bind=True, max_retries=3, name='counting_queue')
def counting_queue(self, ballot_id):
    """
    Celery task tự động kiểm phiếu cho ballot
    
    Args:
        ballot_id: ID của ballot cần kiểm
    
    Returns:
        dict: Kết quả kiểm phiếu
    """
    try:
        # Lấy ballot từ database
        try:
            ballot = Ballot.objects.get(ballot_id=ballot_id)
        except Ballot.DoesNotExist:
            from django.db import connection
            connection.close()
            return {
                'success': False,
                'error': f'Ballot {ballot_id} không tồn tại'
            }
        
        poll = ballot.poll
        
        # Kiểm tra Poll có bật kiểm phiếu tự động không
        if not poll.is_counting_started:
            print(f"[COUNTING QUEUE] Poll {poll.poll_id} chưa bật kiểm tự động, bỏ qua ballot {ballot_id}")
            from django.db import connection
            connection.close()
            return {
                'success': False,
                'error': 'Poll chưa bật kiểm phiếu tự động'
            }
        
        # Kiểm tra ballot đã hoàn thành xử lý ảnh chưa
        if ballot.process_status != 'completed':
            if ballot.process_status == 'pending':
                # Ballot đang chờ xử lý, retry sau 30 giây
                print(f"[COUNTING QUEUE] Ballot {ballot_id} đang pending, retry sau 30s")
                raise self.retry(countdown=30, max_retries=20)
            else:
                return {
                    'success': False,
                    'error': f'Ballot chưa hoàn thành xử lý ảnh (status: {ballot.process_status})'
                }
        
        # Kiểm tra ballot đã được kiểm chưa (dựa vào counting_status)
        if ballot.counting_status == 'completed':
            print(f"[COUNTING QUEUE] Ballot {ballot_id} đã được kiểm (counting_status=completed), bỏ qua")
            return {
                'success': False,
                'error': 'Ballot đã được kiểm'
            }
        
        # Kiểm tra có cấu hình không
        if not poll.config_number:
            print(f"[COUNTING QUEUE] Poll {poll.poll_id} chưa có cấu hình, bỏ qua ballot {ballot_id}")
            return {
                'success': False,
                'error': 'Poll chưa có cấu hình kiểm phiếu'
            }
        
        print(f"[COUNTING QUEUE] Bắt đầu kiểm phiếu cho ballot {ballot_id}")
        
        # Xóa kết quả cũ nếu có
        AIModelResult.objects.filter(ballot=ballot).delete()
        
        # Cập nhật counting_status sang processing
        ballot.counting_status = 'processing'
        ballot.counting_error = None
        ballot.save(update_fields=['counting_status', 'counting_error'])
        
        # Tạo AIModelResult mới
        ai_result = AIModelResult.objects.create(
            ballot=ballot,
            status='processing'
        )
        
        # Áp dụng cấu hình
        config_number = poll.config_number
        
        if config_model.is_valid_config(config_number):
            config_model.apply_config(ai_result, config_number)
        else:
            ai_result.status = 'failed'
            ai_result.error_message = f'Cấu hình không hợp lệ: {config_number}'
            ai_result.save()
            return {
                'success': False,
                'error': ai_result.error_message
            }
        
        # Lấy cấu hình
        rows, cols = ai_result.get_table_dimensions()
        all_cell_models = ai_result.get_all_cell_models()
        
        if not all_cell_models:
            ai_result.status = 'failed'
            ai_result.error_message = 'Không có cấu hình cell nào'
            ai_result.save()
            return {
                'success': False,
                'error': ai_result.error_message
            }
        
        start_time = time.time()
        
        # BƯỚC 1: Chuẩn bị batch requests (gom ảnh theo model)
        print(f"[COUNTING QUEUE] Chuẩn bị batch requests cho ballot {ballot_id}")
        vietnameocr_batch, resnet18_x_batch, resnet18_crossed_batch = prepare_batch_requests(ballot, ai_result, all_cell_models)
        
        print(
            f"[COUNTING QUEUE] model_vietnameocr batch: {len(vietnameocr_batch['image_paths'])} anh, "
            f"model_resnet18_x batch: {len(resnet18_x_batch['image_paths'])} anh, "
            f"model_resnet18_crossed batch: {len(resnet18_crossed_batch['image_paths'])} anh"
        )
        
        # BƯỚC 2: Gửi batch requests tới AI server
        vietnameocr_response = None
        resnet18_x_response = None
        resnet18_crossed_response = None
        
        try:
            # Gui VietNameOCR batch neu co
            if vietnameocr_batch['image_paths']:
                print(f"[COUNTING QUEUE] Gui model_vietnameocr batch voi {len(vietnameocr_batch['image_paths'])} anh")
                vietnameocr_response = send_batch_request(
                    api_url=get_model_api_url(MODEL_VIETNAMEOCR),
                    image_paths=vietnameocr_batch['image_paths'],
                    timeout=settings.AI_SERVER_REQUEST_TIMEOUT
                )
                
                # Kiểm tra response
                if not vietnameocr_response.get('success'):
                    error_msg = vietnameocr_response.get('error', 'model_vietnameocr API tra ve loi')
                    raise requests.exceptions.RequestException(f"model_vietnameocr error: {error_msg}")
            
            # Gui model_resnet18_x batch neu co
            if resnet18_x_batch['image_paths']:
                print(f"[COUNTING QUEUE] Gui model_resnet18_x batch voi {len(resnet18_x_batch['image_paths'])} anh")
                
                
                resnet18_x_response = send_batch_request(
                    api_url=get_model_api_url(MODEL_RESNET18_X),
                    image_paths=resnet18_x_batch['image_paths'],
                    timeout=settings.AI_SERVER_REQUEST_TIMEOUT
                )
                
                # Kiểm tra response
                if not resnet18_x_response.get('success'):
                    error_msg = resnet18_x_response.get('error', 'model_resnet18_x API tra ve loi')
                    raise requests.exceptions.RequestException(f"model_resnet18_x error: {error_msg}")

            if resnet18_crossed_batch['image_paths']:
                print(f"[COUNTING QUEUE] Gui model_resnet18_crossed batch voi {len(resnet18_crossed_batch['image_paths'])} anh")
                resnet18_crossed_response = send_batch_request(
                    api_url=get_model_api_url(MODEL_RESNET18_CROSSED),
                    image_paths=resnet18_crossed_batch['image_paths'],
                    timeout=settings.AI_SERVER_REQUEST_TIMEOUT
                )

                if not resnet18_crossed_response.get('success'):
                    error_msg = resnet18_crossed_response.get('error', 'model_resnet18_crossed API tra ve loi')
                    raise requests.exceptions.RequestException(f"model_resnet18_crossed error: {error_msg}")
                    
        except requests.exceptions.RequestException as e:
            # Lỗi kết nối hoặc API error, retry với exponential backoff
            error_msg = str(e)
            print(f"[COUNTING QUEUE ERROR] {error_msg}")
            
            if self.request.retries < self.max_retries:
                backoff_time = 30 * (self.request.retries + 1)
                print(f"[COUNTING QUEUE] Retry lần {self.request.retries + 1}/{self.max_retries} sau {backoff_time}s")
                
                # Cập nhật trạng thái failed tạm thời
                ai_result.status = 'failed'
                ai_result.error_message = f'Retry {self.request.retries + 1}/{self.max_retries}: {error_msg}'
                ai_result.save()
                
                # Cập nhật counting_status
                ballot.counting_status = 'processing'
                ballot.counting_error = f'Retry {self.request.retries + 1}/{self.max_retries}'
                ballot.save(update_fields=['counting_status', 'counting_error'])
                
                raise self.retry(exc=e, countdown=backoff_time)
            else:
                # Vượt quá max retries
                ai_result.status = 'failed'
                ai_result.error_message = f'AI server không khả dụng sau {self.max_retries} lần thử: {error_msg}'
                ai_result.save()
                
                # Cập nhật counting_status = failed
                ballot.counting_status = 'failed'
                ballot.counting_error = ai_result.error_message
                ballot.save(update_fields=['counting_status', 'counting_error'])
                
                from django.db import connection
                connection.close()
                
                return {
                    'success': False,
                    'ballot_id': ballot_id,
                    'error': ai_result.error_message
                }
        
        # BƯỚC 3: Xử lý responses và lưu vào database
        print(f"[COUNTING QUEUE] Xử lý responses cho ballot {ballot_id}")
        total_processed_cells = process_batch_responses(
            ai_result, 
            vietnameocr_batch,
            resnet18_x_batch,
            resnet18_crossed_batch,
            vietnameocr_response,
            resnet18_x_response,
            resnet18_crossed_response
        )

        # Buoc 3.1: Kiem tra hop le cua phieu dua tren ket qua model_resnet18_x
        is_valid_by_marks = config_model.evaluate_ballot_validity(ai_result, config_number)
        ballot.is_valid = is_valid_by_marks
        ballot.save(update_fields=['is_valid'])
        
        # Cập nhật trạng thái thành công
        processing_time = time.time() - start_time
        ai_result.status = 'success'
        ai_result.processing_time = processing_time
        ai_result.save()
        
        # Giải phóng memory
        gc.collect()
        
        print(f"[COUNTING QUEUE] Đã xử lý {total_processed_cells} ô cho ballot {ballot_id} trong {processing_time:.2f}s")
        
        # BƯỚC 4: Tự động tạo BallotSelection từ kết quả
        try:
            selections_count = config_model.create_ballot_selections(ballot, poll, ai_result, config_number)
        except Exception as e:
            error_msg = f"Lỗi tạo BallotSelection cho ballot {ballot_id}: {e}"
            print(f"[COUNTING QUEUE ERROR] {error_msg}")
            
            # Lưu lỗi vào AIModelResult
            try:
                if ai_result:
                    ai_result.status = 'failed'
                    ai_result.error_message = error_msg
                    ai_result.save()
            except:
                pass
            
            # Cập nhật counting_status = failed
            try:
                ballot.counting_status = 'failed'
                ballot.counting_error = error_msg
                ballot.save(update_fields=['counting_status', 'counting_error'])
            except:
                pass
            
            # Đóng connection để tránh leak
            from django.db import connection
            connection.close()
            
            # Không retry vì đã có kết quả AI, chỉ fail ở bước matching
            return {
                'success': False,
                'ballot_id': ballot_id,
                'error': error_msg
            }
        
        # REFRESH ballot từ database để đảm bảo có trạng thái mới nhất
        ballot.refresh_from_db()
        
        # KIỂM TRA LẠI process_status trước khi set counting_status=completed
        # Đảm bảo upload process đã hoàn thành
        if ballot.process_status != 'completed':
            error_msg = f'Ballot {ballot_id} chưa hoàn thành upload (process_status: {ballot.process_status}). Không thể hoàn thành counting.'
            print(f"[COUNTING QUEUE ERROR] {error_msg}")
            
            # Cập nhật counting_status = failed
            ballot.counting_status = 'failed'
            ballot.counting_error = error_msg
            ballot.save(update_fields=['counting_status', 'counting_error'])
            
            return {
                'success': False,
                'ballot_id': ballot_id,
                'error': error_msg
            }
        
        # Cập nhật trạng thái ballot: counting_status = completed (is_checked tự động = True qua property)
        ballot.counting_status = 'completed'
        ballot.counting_error = None
        ballot.save(update_fields=['counting_status', 'counting_error'])
        
        print(f"[COUNTING QUEUE SUCCESS] Hoàn thành kiểm phiếu ballot {ballot_id}")
        
        # Giải phóng toàn bộ memory trước khi return
        gc.collect()
        
        return {
            'success': True,
            'ballot_id': ballot_id,
            'cells_processed': total_processed_cells,
            'processing_time': processing_time
        }
        
    except Exception as e:
        # Lỗi không xác định
        error_msg = f'Lỗi kiểm phiếu: {str(e)}'
        print(f"[COUNTING QUEUE ERROR] ballot_id={ballot_id}: {error_msg}")
        
        # ĐÓNG TẤT CẢ DATABASE CONNECTIONS ĐỂ TRÁNH LEAK
        from django.db import connection
        connection.close()
        
        try:
            ai_result = AIModelResult.objects.filter(ballot_id=ballot_id).first()
            if ai_result:
                ai_result.status = 'failed'
                ai_result.error_message = error_msg
                ai_result.save()
        except:
            pass
        
        # Cập nhật counting_status = failed
        try:
            ballot = Ballot.objects.get(ballot_id=ballot_id)
            ballot.counting_status = 'failed'
            ballot.counting_error = error_msg
            ballot.save(update_fields=['counting_status', 'counting_error'])
        except:
            pass
        
        # Retry với EXPONENTIAL BACKOFF để tránh retry storm
        if self.request.retries < self.max_retries:
            # Countdown tăng dần: 30s, 60s, 90s
            backoff_time = 30 * (self.request.retries + 1)
            print(f"[COUNTING QUEUE] Retry lần {self.request.retries + 1}/{self.max_retries}, chờ {backoff_time}s")
            raise self.retry(exc=e, countdown=backoff_time)
        
        return {
            'success': False,
            'ballot_id': ballot_id,
            'error': error_msg
        }
