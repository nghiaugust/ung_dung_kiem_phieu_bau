"""
Celery tasks cho xử lý async ballot upload
Tách phần xử lý nặng (làm phẳng ảnh, cắt ô) ra khỏi API request
"""
import os
import gc
import tempfile
from django.conf import settings
from django.core.files import File
from celery import shared_task

from ballot.models import Ballot
from form.models import BallotDocument
from preprocessing.preprocessing_for_upload_step_1 import (
    lam_phang_anh_phieu_bau,
    lam_phang_anh_phieu_bau_tu_diem_moc,
)
from preprocessing.preprocessing_for_upload_step_2 import cat_va_luu_cac_o_phieu_bau_wrapper


@shared_task(bind=True, max_retries=3, name='upload_queue')
def process_ballot_image_task(self, ballot_id, temp_input_path, poll_id, file_ext='jpg'):
    """
    Celery task xử lý ảnh phiếu bầu: làm phẳng và cắt ô
    
    Args:
        ballot_id: ID của ballot cần xử lý
        temp_input_path: Đường dẫn file ảnh tạm (chưa làm phẳng)
        poll_id: ID của poll
        file_ext: Extension của file (jpg, png, ...)
    
    Returns:
        dict: Kết quả xử lý
    """
    temp_output_path = None
    
    try:
        # Lấy ballot từ database
        try:
            ballot = Ballot.objects.get(ballot_id=ballot_id)
        except Ballot.DoesNotExist:
            return {
                'success': False,
                'error': f'Ballot {ballot_id} không tồn tại'
            }
        
        # Cập nhật status sang processing
        ballot.process_status = 'processing'
        ballot.save(update_fields=['process_status'])
        
        # Kiểm tra file input tồn tại NGAY SAU KHI set processing
        if not os.path.exists(temp_input_path):
            ballot.process_status = 'failed'
            ballot.process_error = f'File input không tồn tại: {temp_input_path}'
            ballot.save(update_fields=['process_status', 'process_error'])
            return {
                'success': False,
                'error': ballot.process_error
            }
        
        # Lấy kích thước từ BallotDocument
        try:
            ballot_doc = BallotDocument.objects.filter(poll_id=poll_id).order_by('-created_at').first()
            if ballot_doc:
                chieu_ngang_cm = ballot_doc.marker_distance_horizontal
                chieu_doc_cm = ballot_doc.marker_distance_vertical
                
                if chieu_ngang_cm is None or chieu_doc_cm is None:
                    raise ValueError("BallotDocument không có thông tin kích thước marker")
                
                print(f"[TASK] Sử dụng kích thước từ BallotDocument: {chieu_ngang_cm}cm x {chieu_doc_cm}cm")
            else:
                raise BallotDocument.DoesNotExist()
        except BallotDocument.DoesNotExist:
            # Fallback về kích thước mặc định
            chieu_ngang_cm = 18.0
            chieu_doc_cm = 25.5
            print(f"[TASK] Sử dụng kích thước mặc định: {chieu_ngang_cm}cm x {chieu_doc_cm}cm")
        
        # Tạo file output tạm
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as temp_output:
            temp_output_path = temp_output.name
        
        # STEP 1: Làm phẳng ảnh và lấy data QR
        print(f"[TASK] Bắt đầu làm phẳng ảnh cho ballot_id={ballot_id}")
        client_detection = ballot.metadata.get('client_detection') if isinstance(ballot.metadata, dict) else None
        used_client_detection = False

        if isinstance(client_detection, dict) and client_detection.get('src_points'):
            try:
                print(f"[TASK] Dung diem moc tu app de lam phang ballot_id={ballot_id}")
                warped_image, qr_data_raw = lam_phang_anh_phieu_bau_tu_diem_moc(
                    duong_dan_anh_dau_vao=temp_input_path,
                    duong_dan_anh_dau_ra=temp_output_path,
                    client_detection=client_detection,
                    chieu_ngang_cm=chieu_ngang_cm,
                    chieu_doc_cm=chieu_doc_cm,
                    dpi=300
                )
                used_client_detection = True
            except ValueError as metadata_error:
                print(f"[TASK WARNING] Metadata app khong dung, fallback detect tren server: {metadata_error}")
                warped_image, qr_data_raw = lam_phang_anh_phieu_bau(
                    duong_dan_anh_dau_vao=temp_input_path,
                    duong_dan_anh_dau_ra=temp_output_path,
                    chieu_ngang_cm=chieu_ngang_cm,
                    chieu_doc_cm=chieu_doc_cm,
                    dpi=300
                )
        else:
            warped_image, qr_data_raw = lam_phang_anh_phieu_bau(
                duong_dan_anh_dau_vao=temp_input_path,
                duong_dan_anh_dau_ra=temp_output_path,
                chieu_ngang_cm=chieu_ngang_cm,
                chieu_doc_cm=chieu_doc_cm,
                dpi=300
            )
        
        # Giải phóng memory ngay sau khi làm phẳng (warped_image có thể rất lớn)
        del warped_image
        gc.collect()
        
        # Kiểm tra kết quả làm phẳng
        if not os.path.exists(temp_output_path):
            ballot.process_status = 'failed'
            ballot.process_error = 'Không tạo được file ảnh đã làm phẳng'
            ballot.save(update_fields=['process_status', 'process_error'])
            return {
                'success': False,
                'error': ballot.process_error
            }
        
        # Lưu file đã làm phẳng vào ballot_image
        print(f"[TASK] Lưu ảnh đã làm phẳng cho ballot_id={ballot_id}")
        with open(temp_output_path, 'rb') as f:
            ballot.ballot_image.save(
                f'{ballot.ballot_id}.jpg',
                File(f),
                save=False
            )
        
        # Update metadata với QR code raw
        if ballot.metadata:
            ballot.metadata.update({
                'qr_code_raw': qr_data_raw,
                'processed_at': str(ballot.timestamp),
                'flattening_source': 'client_detection' if used_client_detection else 'server_detection'
            })
        else:
            ballot.metadata = {
                'qr_code_raw': qr_data_raw,
                'processed_at': str(ballot.timestamp),
                'flattening_source': 'client_detection' if used_client_detection else 'server_detection'
            }
        
        ballot.save()
        
        # STEP 2: Cắt và lưu các ô phiếu bầu
        print(f"[TASK] Bắt đầu cắt cells cho ballot_id={ballot_id}")
        ballot_image_full_path = os.path.join(settings.MEDIA_ROOT, ballot.ballot_image.name)
        
        preprocessing_result = cat_va_luu_cac_o_phieu_bau_wrapper(ballot, ballot_image_full_path)
        print(f"[TASK] Hoàn thành cắt cells cho ballot_id={ballot_id}")
        
        # Lưu tọa độ các đường kẻ ngang vào metadata
        if preprocessing_result.get('status') == 'success':
            horizontal_lines = preprocessing_result.get('horizontal_lines', [])
            vertical_lines = preprocessing_result.get('vertical_lines', [])
            
            # Cập nhật metadata với thông tin đường kẻ
            ballot.metadata['horizontal_lines'] = horizontal_lines
            ballot.metadata['vertical_lines'] = vertical_lines
            ballot.save(update_fields=['metadata'])
            
            print(f"[TASK] Đã lưu tọa độ {len(horizontal_lines)} đường ngang và {len(vertical_lines)} đường dọc vào metadata")
        
        # Giải phóng memory sau khi cắt cells xong
        gc.collect()
        
        # Cập nhật status sang completed
        ballot.process_status = 'completed'
        ballot.process_error = None
        ballot.save(update_fields=['process_status', 'process_error'])
        
        print(f"[TASK SUCCESS] Hoàn thành xử lý ballot_id={ballot_id}")
        
        # Kiểm tra nếu Poll đã bật kiểm phiếu tự động
        ballot.refresh_from_db()
        poll = ballot.poll
        
        if poll and poll.is_counting_started:
            # Đẩy ballot vào queue kiểm phiếu tự động
            print(f"[AUTO COUNTING] Poll {poll.poll_id} đã bật tự động kiểm phiếu, đẩy ballot {ballot_id} vào counting queue")
            from counting.tasks import counting_queue
            counting_queue.delay(ballot_id)
        
        # Giải phóng toàn bộ memory trước khi return (quan trọng!)
        gc.collect()
        
        return {
            'success': True,
            'ballot_id': ballot_id,
            'qr_data_raw': qr_data_raw
        }
        
    except ValueError as e:
        # Lỗi từ làm phẳng ảnh (thiếu markers)
        error_msg = f'Lỗi làm phẳng ảnh: {str(e)}'
        print(f"[TASK ERROR] ballot_id={ballot_id}: {error_msg}")
        
        # ĐÓNG DATABASE CONNECTIONS ĐỂ TRÁNH LEAK
        from django.db import connection
        connection.close()
        
        try:
            ballot = Ballot.objects.get(ballot_id=ballot_id)
            ballot.process_status = 'failed'
            ballot.process_error = error_msg
            ballot.save(update_fields=['process_status', 'process_error'])
        except:
            pass
        
        return {
            'success': False,
            'ballot_id': ballot_id,
            'error': error_msg
        }
        
    except Exception as e:
        # Lỗi khác
        error_msg = f'Lỗi không xác định: {str(e)}'
        print(f"[TASK ERROR] ballot_id={ballot_id}: {error_msg}")
        
        # ĐÓNG DATABASE CONNECTIONS ĐỂ TRÁNH LEAK
        from django.db import connection
        connection.close()
        
        try:
            ballot = Ballot.objects.get(ballot_id=ballot_id)
            ballot.process_status = 'failed'
            ballot.process_error = error_msg
            ballot.save(update_fields=['process_status', 'process_error'])
        except:
            pass
        
        # Retry với exponential backoff
        if self.request.retries < self.max_retries:
            backoff_time = 60 * (self.request.retries + 1)  # 60s, 120s, 180s
            print(f"[TASK] Retry lần {self.request.retries + 1}/{self.max_retries}, chờ {backoff_time}s")
            raise self.retry(exc=e, countdown=backoff_time)
        
        return {
            'success': False,
            'ballot_id': ballot_id,
            'error': error_msg
        }
        
    finally:
        # Cleanup: Xóa file tạm
        if temp_input_path and os.path.exists(temp_input_path):
            try:
                os.unlink(temp_input_path)
                print(f"[TASK] Đã xóa temp input: {temp_input_path}")
            except Exception as e:
                print(f"[TASK WARNING] Không thể xóa temp input: {e}")
        
        if temp_output_path and os.path.exists(temp_output_path):
            try:
                os.unlink(temp_output_path)
                print(f"[TASK] Đã xóa temp output: {temp_output_path}")
            except Exception as e:
                print(f"[TASK WARNING] Không thể xóa temp output: {e}")


# ============================================
# CELERY PERIODIC TASK - Tự động cleanup hậu kiểm
# ============================================

@shared_task(name='auto_cleanup_checking_timeout')
def auto_cleanup_checking_timeout():
    """
    Celery periodic task tự động thu hồi phiếu hậu kiểm bị timeout
    Chỉ chạy khi Poll có is_checking_started = True
    
    Chạy mỗi 3 phút (cấu hình trong celery.py beat_schedule)
    """
    from poll.models import Poll
    from api.checking_timeout import cleanup_checking_stuck_tasks
    
    # Tìm tất cả Poll đang bật tính năng hậu kiểm tự động
    active_polls = Poll.objects.filter(is_checking_started=True)
    
    total_recovered = 0
    for poll in active_polls:
        print(f"[AUTO CLEANUP] Checking poll_id={poll.poll_id}: {poll.title}")
        
        # Gọi cleanup_checking_stuck_tasks cho poll này
        result = cleanup_checking_stuck_tasks(timeout_minutes=5, poll_id=poll.poll_id)
        
        if result.get('success'):
            recovered = result.get('recovered', 0)
            total_recovered += recovered
            if recovered > 0:
                print(f"[AUTO CLEANUP] Poll {poll.poll_id}: Thu hồi được {recovered} phiếu")
    
    print(f"[AUTO CLEANUP] Hoàn thành - Tổng thu hồi: {total_recovered} phiếu")
    return {
        'success': True,
        'total_recovered': total_recovered,
        'active_polls': active_polls.count()
    }
