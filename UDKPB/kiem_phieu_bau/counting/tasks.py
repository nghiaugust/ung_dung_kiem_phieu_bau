"""
Celery tasks cho kiểm phiếu tự động
"""
import os
import gc
import time
import difflib
import requests
import json
from typing import Dict, List, Tuple
from django.conf import settings
from celery import shared_task

from ballot.models import Ballot, BallotSelection
from poll.models import Poll, Candidate
from preprocessing.models import BallotCell
from counting.models import AIModelResult
from counting import config_model


AI_TROCR_API_URL = f"{settings.AI_SERVER_BASE_URL}/api/trocr/recognize/"
AI_YOLO_API_URL = f"{settings.AI_SERVER_BASE_URL}/api/yolo/detect/"


def prepare_batch_requests(ballot, ai_result, all_cell_models):
    """
    Chuẩn bị và gom các ảnh theo model thành batch để gửi request
    
    Args:
        ballot: Ballot object
        ai_result: AIModelResult object
        all_cell_models: Dict mapping cell_key -> model_name
        
    Returns:
        Tuple[Dict, Dict]: (trocr_batch, yolo_batch)
            - trocr_batch: {'image_paths': [...], 'cell_mapping': {idx: (row, col)}}
            - yolo_batch: {'image_paths': [...], 'cell_mapping': {idx: (row, col)}}
    """
    trocr_batch = {'image_paths': [], 'cell_mapping': {}}
    yolo_batch = {'image_paths': [], 'cell_mapping': {}}
    
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
        if model_name == 'trocr':
            idx = len(trocr_batch['image_paths'])
            trocr_batch['image_paths'].append(cell_image_path)
            trocr_batch['cell_mapping'][idx] = (row, col)
        elif model_name == 'yolo':
            idx = len(yolo_batch['image_paths'])
            yolo_batch['image_paths'].append(cell_image_path)
            yolo_batch['cell_mapping'][idx] = (row, col)
    
    return trocr_batch, yolo_batch


def process_batch_responses(ai_result, trocr_batch, yolo_batch, trocr_response, yolo_response):
    """
    Xử lý kết quả trả về từ API và lưu vào database
    
    Args:
        ai_result: AIModelResult object
        trocr_batch: Dict chứa thông tin batch TrOCR
        yolo_batch: Dict chứa thông tin batch YOLO
        trocr_response: Response từ TrOCR API
        yolo_response: Response từ YOLO API
        
    Returns:
        int: Số lượng cells đã xử lý thành công
    """
    total_processed_cells = 0
    
    # Xử lý TrOCR response
    if trocr_response and trocr_response.get('success') and trocr_response.get('results'):
        results = trocr_response['results']
        for idx, result in enumerate(results):
            if idx in trocr_batch['cell_mapping']:
                row, col = trocr_batch['cell_mapping'][idx]
                recognized_text = result.get('text', '')
                confidence = result.get('confidence', 0)
                
                ai_result.set_cell_result(row, col, recognized_text, confidence)
                total_processed_cells += 1
    
    # Xử lý YOLO response
    if yolo_response and yolo_response.get('success') and yolo_response.get('results'):
        results = yolo_response['results']
        for idx, result in enumerate(results):
            if idx in yolo_batch['cell_mapping']:
                row, col = yolo_batch['cell_mapping'][idx]
                label = result.get('label', 'none')
                detections = result.get('detections', [])
                
                # Lấy confidence cao nhất
                confidence = 0
                if detections:
                    max_conf_detection = max(detections, key=lambda d: d.get('confidence', 0))
                    confidence = max_conf_detection.get('confidence', 0)
                
                # Lưu kết quả (label + detections)
                result_data = {
                    'label': label,
                    'detections': detections
                }
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


def create_ballot_selections(ballot, poll, ai_result, config_number):
    """
    Tự động tạo BallotSelection từ kết quả AI
    
    Args:
        ballot: Ballot object
        poll: Poll object
        ai_result: AIModelResult object
        config_number: Số cấu hình (1 hoặc 2)
        
    Returns:
        int: Số lượng BallotSelection đã tạo
        
    Raises:
        Exception: Khi có lỗi trong quá trình tạo selections
    """
    # Lấy danh sách ứng viên
    candidate_list = list(Candidate.objects.filter(poll=poll).order_by('candidate_id'))
    candidate_names = {c.candidate_id: c.name for c in candidate_list}
    
    # Xóa BallotSelection cũ của ballot này
    BallotSelection.objects.filter(ballot=ballot).delete()
    
    selections_to_create = []
    
    # Lấy config để biết start_row
    start_row = 1  # Dòng 2 trong UI → index 1 trong DB
    
    # Lấy tất cả cells có YOLO
    yolo_cells = ai_result.get_cells_by_model('yolo')
    
    # Lấy tất cả cells có TrOCR (nếu có)
    trocr_cells = ai_result.get_cells_by_model('trocr')
    
    # Group theo row để xử lý từng dòng
    rows_dict = {}
    for cell_key, cell_data in yolo_cells.items():
        row, col = map(int, cell_key.split('_'))
        if row not in rows_dict:
            rows_dict[row] = {'yolo': [], 'trocr': None}
        rows_dict[row]['yolo'].append((col, cell_data))
    
    # Thêm TrOCR vào rows_dict
    for cell_key, cell_data in trocr_cells.items():
        row, col = map(int, cell_key.split('_'))
        if row not in rows_dict:
            rows_dict[row] = {'yolo': [], 'trocr': None}
        rows_dict[row]['trocr'] = cell_data
    
    # Xử lý từng dòng
    for row, row_data in rows_dict.items():
        yolo_results = row_data['yolo']
        trocr_result = row_data['trocr']
        
        # Sắp xếp yolo_results theo col để lấy đúng cột đồng ý (cột đầu tiên)
        yolo_results.sort(key=lambda x: x[0])
        
        if not yolo_results:
            continue
        
        # Lấy cột đồng ý (cột đầu tiên)
        agree_col, agree_result = yolo_results[0]
        result_data = agree_result.get('result', {})
        
        if isinstance(result_data, dict):
            label = result_data.get('label', 'none')
        else:
            continue
        
        # Kiểm tra có dấu X không
        if 'x_mark' not in label.lower():
            continue
        
        # Xác định candidate dựa trên config_number
        candidate_to_select = None
        
        if config_number == 1 and trocr_result:
            # Config1: Sử dụng TrOCR để matching tên
            recognized_name = trocr_result.get('result', '').strip()
            
            if recognized_name and recognized_name != "[Lỗi TrOCR]":
                # Tìm candidate giống nhất với recognized_name
                best_match_id = None
                best_match_ratio = 0.0
                
                for candidate_id, candidate_name in candidate_names.items():
                    # Sử dụng difflib để so sánh tên
                    ratio = difflib.SequenceMatcher(
                        None, 
                        recognized_name.upper(), 
                        candidate_name.upper()
                    ).ratio()
                    
                    if ratio > best_match_ratio:
                        best_match_ratio = ratio
                        best_match_id = candidate_id
                
                # Chỉ chọn nếu tỉ lệ khớp >= 0.6 (60%)
                if best_match_id and best_match_ratio >= 0.6:
                    candidate_to_select = next(
                        (c for c in candidate_list if c.candidate_id == best_match_id),
                        None
                    )
        else:
            # Config2: Sử dụng thứ tự dòng
            candidate_index = row - start_row
            
            if 0 <= candidate_index < len(candidate_list):
                candidate_to_select = candidate_list[candidate_index]
        
        # Tạo BallotSelection nếu đã xác định được candidate
        if candidate_to_select:
            selections_to_create.append(
                BallotSelection(
                    ballot=ballot,
                    candidate_id=candidate_to_select.candidate_id
                )
            )
    
    # Bulk create
    if selections_to_create:
        BallotSelection.objects.bulk_create(selections_to_create)
    
    return len(selections_to_create)


def _has_x_mark(result_data):
    if isinstance(result_data, dict):
        label = result_data.get('label', '')
    else:
        label = str(result_data) if result_data is not None else ''
    return 'x_mark' in str(label).lower()


def evaluate_ballot_validity(ai_result):
    """
    Kiểm tra hợp lệ dựa trên 2 ô đồng ý/không đồng ý mỗi dòng.
    Hợp lệ khi mỗi dòng có đúng 1 dấu X.
    """
    cell_models = ai_result.get_all_cell_models()
    cell_results = ai_result.get_all_cell_results()

    rows = {}
    for cell_key, model_name in cell_models.items():
        if model_name != 'yolo':
            continue
        try:
            row, col = map(int, cell_key.split('_'))
        except ValueError:
            continue
        if row not in rows:
            rows[row] = {}
        rows[row][col] = cell_results.get(cell_key, {}).get('result')

    if not rows:
        return True

    for col_results in rows.values():
        mark_count = 0
        for result in col_results.values():
            if _has_x_mark(result):
                mark_count += 1
        if mark_count == 0 or mark_count > 1:
            return False

    return True


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
        
        if config_number == 1:
            config_model.apply_config1(ai_result)
        elif config_number == 2:
            config_model.apply_config2(ai_result)
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
        trocr_batch, yolo_batch = prepare_batch_requests(ballot, ai_result, all_cell_models)
        
        print(f"[COUNTING QUEUE] TrOCR batch: {len(trocr_batch['image_paths'])} ảnh, YOLO batch: {len(yolo_batch['image_paths'])} ảnh")
        
        # BƯỚC 2: Gửi batch requests tới AI server
        trocr_response = None
        yolo_response = None
        
        try:
            # Gửi TrOCR batch nếu có
            if trocr_batch['image_paths']:
                print(f"[COUNTING QUEUE] Gửi TrOCR batch với {len(trocr_batch['image_paths'])} ảnh")
                trocr_response = send_batch_request(
                    api_url=AI_TROCR_API_URL,
                    image_paths=trocr_batch['image_paths'],
                    timeout=settings.AI_SERVER_REQUEST_TIMEOUT
                )
                
                # Kiểm tra response
                if not trocr_response.get('success'):
                    error_msg = trocr_response.get('error', 'TrOCR API trả về lỗi')
                    raise requests.exceptions.RequestException(f"TrOCR error: {error_msg}")
            
            # Gửi YOLO batch nếu có
            if yolo_batch['image_paths']:
                print(f"[COUNTING QUEUE] Gửi YOLO batch với {len(yolo_batch['image_paths'])} ảnh")
                
                # Chuẩn bị image_paths_map cho YOLO
                image_paths_map = {}
                for path in yolo_batch['image_paths']:
                    filename = os.path.basename(path)
                    image_paths_map[filename] = path
                
                yolo_response = send_batch_request(
                    api_url=AI_YOLO_API_URL,
                    image_paths=yolo_batch['image_paths'],
                    extra_data={'image_paths': json.dumps(image_paths_map)},
                    timeout=settings.AI_SERVER_REQUEST_TIMEOUT
                )
                
                # Kiểm tra response
                if not yolo_response.get('success'):
                    error_msg = yolo_response.get('error', 'YOLO API trả về lỗi')
                    raise requests.exceptions.RequestException(f"YOLO error: {error_msg}")
                    
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
            trocr_batch, 
            yolo_batch, 
            trocr_response, 
            yolo_response
        )

        # BƯỚC 3.1: Kiểm tra hợp lệ của phiếu dựa trên kết quả YOLO
        is_valid_by_marks = evaluate_ballot_validity(ai_result)
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
            selections_count = create_ballot_selections(ballot, poll, ai_result, config_number)
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
