"""
Celery tasks cho kiểm phiếu tự động
"""
import os
import gc
import time
import difflib
import requests
from django.conf import settings
from celery import shared_task

from ballot.models import Ballot, BallotSelection
from poll.models import Poll, Candidate
from preprocessing.models import BallotCell
from counting.models import AIModelResult
from counting import config_model


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
        
        # Kiểm tra ballot đã được kiểm chưa
        if ballot.is_checked:
            print(f"[COUNTING QUEUE] Ballot {ballot_id} đã được kiểm, bỏ qua")
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
        
        # Kiểm tra AI server có sẵn sàng không
        try:
            health_response = requests.get('http://localhost:8080/api/health/', timeout=0.5)
            if health_response.status_code != 200:
                raise Exception("AI server not healthy")
        except Exception as e:
            # AI server chưa sẵn sàng, retry với EXPONENTIAL BACKOFF
            if self.request.retries < self.max_retries:
                # Countdown tăng dần: 30s, 60s, 90s
                backoff_time = 30 * (self.request.retries + 1)
                print(f"[COUNTING QUEUE] AI server chưa sẵn sàng ({e}), retry lần {self.request.retries + 1}/{self.max_retries} sau {backoff_time}s")
                raise self.retry(exc=e, countdown=backoff_time)
            else:
                # Vượt quá max retries, fail ngay
                error_msg = f'AI server không khả dụng sau {self.max_retries} lần thử: {str(e)}'
                print(f"[COUNTING QUEUE ERROR] {error_msg}")
                ai_result = AIModelResult.objects.create(
                    ballot=ballot,
                    status='failed',
                    error_message=error_msg
                )
                from django.db import connection
                connection.close()
                return {
                    'success': False,
                    'ballot_id': ballot_id,
                    'error': error_msg
                }
        
        print(f"[COUNTING QUEUE] Bắt đầu kiểm phiếu cho ballot {ballot_id}")
        
        # Xóa kết quả cũ nếu có
        AIModelResult.objects.filter(ballot=ballot).delete()
        
        # Tạo AIModelResult mới
        ai_result = AIModelResult.objects.create(
            ballot=ballot,
            status='processing'
        )
        
        # Áp dụng cấu hình
        config_number = poll.config_number
        config_type = f'config{config_number}'
        
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
        
        # Import hàm gọi API
        from counting.views import call_trocr_api, call_yolo_api
        
        total_processed_cells = 0
        start_time = time.time()
        
        # Xử lý từng ô theo cấu hình
        for cell_key, model_name in all_cell_models.items():
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
            
            # Gọi model tương ứng
            if model_name == 'trocr':
                # Gọi TrOCR API
                trocr_result = call_trocr_api([cell_image_path])
                
                if trocr_result.get('success') and trocr_result.get('results'):
                    recognized_text = trocr_result['results'][0].get('text', '')
                    confidence = trocr_result['results'][0].get('confidence', 0)
                    
                    # Lưu kết quả vào result_model
                    ai_result.set_cell_result(row, col, recognized_text, confidence)
                    total_processed_cells += 1
                else:
                    ai_result.set_cell_result(row, col, "[Lỗi TrOCR]", 0)
            
            elif model_name == 'yolo':
                # Gọi YOLO API
                yolo_result = call_yolo_api([cell_image_path])
                
                if yolo_result.get('success') and yolo_result.get('results'):
                    detection = yolo_result['results'][0]
                    label = detection.get('label', 'none')
                    detections = detection.get('detections', [])
                    
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
                else:
                    ai_result.set_cell_result(row, col, "[Lỗi YOLO]", 0)
        
        # Cập nhật trạng thái thành công
        processing_time = time.time() - start_time
        ai_result.status = 'success'
        ai_result.processing_time = processing_time
        ai_result.save()
        
        # Giải phóng memory sau khi xử lý cells xong
        gc.collect()
        
        print(f"[COUNTING QUEUE] Đã xử lý {total_processed_cells} ô cho ballot {ballot_id} trong {processing_time:.2f}s")
        
        # Tự động tạo BallotSelection từ kết quả
        try:
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
                print(f"[COUNTING QUEUE] ✅ Đã tạo {len(selections_to_create)} lựa chọn cho ballot {ballot_id}")
            
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
        
        # KIỂM TRA LẠI process_status trước khi set is_checked=True
        # Tránh race condition với upload task
        if ballot.process_status != 'completed':
            error_msg = f'Ballot {ballot_id} không còn ở trạng thái completed (hiện tại: {ballot.process_status}). Không thể đánh dấu is_checked.'
            print(f"[COUNTING QUEUE ERROR] {error_msg}")
            return {
                'success': False,
                'ballot_id': ballot_id,
                'error': error_msg
            }
        
        # Cập nhật trạng thái ballot
        ballot.is_checked = True
        ballot.save(update_fields=['is_checked'])
        
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
        
        # Retry với EXPONENTIAL BACKOFF để tránh retry storm
        if self.request.retries < self.max_retries:
            # Countdown tăng dần: 30s, 60s, 90s, 120s, ...
            backoff_time = 30 * (self.request.retries + 1)
            print(f"[COUNTING QUEUE] Retry lần {self.request.retries + 1}/{self.max_retries}, chờ {backoff_time}s")
            raise self.retry(exc=e, countdown=backoff_time)
        
        return {
            'success': False,
            'ballot_id': ballot_id,
            'error': error_msg
        }
