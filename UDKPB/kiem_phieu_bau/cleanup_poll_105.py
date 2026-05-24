#!/usr/bin/env python
"""
Script để xóa dữ liệu cho một poll:
- Mặc định tự chọn poll hiện tại (poll có dữ liệu mới nhất)
- Có thể chỉ định poll bằng --poll-id
- Xóa tất cả ballot_image của các ballot thuộc poll
- Reset counting_status = pending, checking_status = NEW, input_by = null, process_status = no_upload, checking_locked_by = null, checking_locked_at = null
- Xóa tất cả ballot_cell liên quan đến poll
- Xóa tất cả preprocessed_ballot liên quan đến poll
- Xóa tất cả ai_model_result liên quan đến poll
"""

import os
import sys
import argparse
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiem_phieu_bau.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from ballot.models import Ballot, BallotSelection
from preprocessing.models import PreprocessedBallot, BallotCell
from counting.models import AIModelResult
from poll.models import Poll
from django.db import transaction


# Sửa ID poll cần cleanup tại đây nếu không muốn truyền tham số --poll-id.
# Đặt None nếu muốn script tự chọn poll hiện tại như logic cũ.
POLL_ID_TO_CLEANUP = 109


def get_current_poll_id():
    """Lấy poll hiện tại dựa trên dữ liệu ballot gần nhất trong hệ thống."""
    latest_with_image = (
        Ballot.objects
        .filter(poll_id__isnull=False)
        .exclude(ballot_image__isnull=True)
        .exclude(ballot_image='')
        .order_by('-timestamp')
        .first()
    )
    if latest_with_image:
        return latest_with_image.poll_id

    latest_with_ballot = (
        Ballot.objects
        .filter(poll_id__isnull=False)
        .order_by('-timestamp')
        .first()
    )
    if latest_with_ballot:
        return latest_with_ballot.poll_id

    latest_poll = Poll.objects.order_by('-poll_id').first()
    if latest_poll:
        return latest_poll.poll_id

    return None


def cleanup_poll(poll_id):
    """
    Xóa tất cả dữ liệu liên quan đến một poll:
    1. Xóa ballot_image của tất cả ballots
    2. Reset counting_status = pending, checking_status = NEW, input_by = null, process_status = no_upload, checking_locked_by = null, checking_locked_at = null
    3. Xóa tất cả ballot_cell
    4. Xóa tất cả preprocessed_ballot
    5. Xóa tất cả ai_model_result
    """

    print(f"Bắt đầu cleanup dữ liệu cho Poll {poll_id}")
    
    try:
        with transaction.atomic():
            # Lấy tất cả ballot của poll được chọn
            ballots = Ballot.objects.filter(poll_id=poll_id)
            total_ballots = ballots.count()
            
            print(f"Tìm thấy {total_ballots} ballots trong poll {poll_id}")
            
            if total_ballots == 0:
                print("Không có ballot nào được tìm thấy!")
                return
            
            # 1. Xử lý xóa ballot_image
            ballots_with_image = ballots.exclude(ballot_image__isnull=True).exclude(ballot_image='')
            image_count = ballots_with_image.count()
            
            print(f"\n1. Xóa ballot_image:")
            print(f"   - Số ballots có image: {image_count}")
            
            deleted_images = 0
            for ballot in ballots_with_image:
                if ballot.ballot_image:
                    # Xóa file vật lý nếu tồn tại
                    try:
                        if os.path.isfile(ballot.ballot_image.path):
                            os.remove(ballot.ballot_image.path)
                            print(f"   - Đã xóa file: {ballot.ballot_image.path}")
                        deleted_images += 1
                    except Exception as e:
                        print(f"   - Lỗi xóa file {ballot.ballot_image.path}: {e}")
                    
                    # Xóa đường dẫn trong database
                    ballot.ballot_image = None
                    ballot.save(update_fields=['ballot_image'])
            
            print(f"   - Đã xóa {deleted_images} ballot images")
            
            # 2. Reset trường counting_status, checking_status, input_by, process_status và khóa hậu kiểm
            print(f"\n2. Reset trường counting_status, checking_status, input_by, process_status và khóa hậu kiểm:")
            
            updated_ballots = 0
            for ballot in ballots:
                # Reset về trạng thái mặc định (is_checked và is_post_checked là properties)
                ballot.counting_status = 'pending'  # is_checked sẽ tự động = False
                ballot.checking_status = 'NEW'      # is_post_checked sẽ tự động = False
                ballot.input_by = None
                ballot.is_valid = True  # Reset về hợp lệ (nếu có trường hợp nào bị đánh dấu không hợp lệ trước
                ballot.process_status = 'no_upload'
                ballot.checking_locked_by = None
                ballot.checking_locked_at = None
                ballot.save(update_fields=[
                    'counting_status',
                    'checking_status',
                    'input_by',
                    'is_valid',
                    'process_status',
                    'checking_locked_by',
                    'checking_locked_at',
                ])
                updated_ballots += 1
            
            print(f"   - Đã reset {updated_ballots} ballots (counting_status=pending, checking_status=NEW, input_by=null, process_status=no_upload, checking_locked_by=null, checking_locked_at=null)")
            
            preprocessed_ballots = PreprocessedBallot.objects.filter(ballot__poll_id=poll_id)
            preprocessed_count = preprocessed_ballots.count()
            
            print(f"\n3. Xóa BallotCell:")
            print(f"   - Số preprocessed ballots: {preprocessed_count}")
            
            total_cells_deleted = 0
            for preprocessed in preprocessed_ballots:
                cells = BallotCell.objects.filter(preprocessed_ballot=preprocessed)
                cells_count = cells.count()
                
                # Xóa file vật lý của từng cell
                for cell in cells:
                    if cell.cell_image:
                        try:
                            file_path = os.path.join(settings.MEDIA_ROOT, cell.cell_image)
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                        except Exception as e:
                            print(f"   - Lỗi xóa cell image {cell.cell_image}: {e}")
                
                # Xóa tất cả cells trong database
                cells.delete()
                total_cells_deleted += cells_count
                print(f"   - Đã xóa {cells_count} cells cho ballot {preprocessed.ballot.ballot_id}")
            
            print(f"   - Tổng cộng đã xóa {total_cells_deleted} ballot cells")
            
            # 4. Xử lý xóa PreprocessedBallot
            print(f"\n4. Xóa PreprocessedBallot:")
            
            deleted_preprocessed = 0
            for preprocessed in preprocessed_ballots:
                # Xóa detection_image và các file debug
                if preprocessed.detection_image:
                    try:
                        file_path = os.path.join(settings.MEDIA_ROOT, preprocessed.detection_image)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        print(f"   - Lỗi xóa detection image {preprocessed.detection_image}: {e}")
                
                # Xóa các file debug nếu có
                ballot_id = preprocessed.ballot.ballot_id
                ballot_dir = os.path.join(settings.MEDIA_ROOT, 'ballots')
                
                debug_files = [
                    f"ballot_{ballot_id}_edges.jpg",
                    f"ballot_{ballot_id}_histogram.png"
                ]
                
                for debug_file in debug_files:
                    debug_path = os.path.join(ballot_dir, debug_file)
                    try:
                        if os.path.isfile(debug_path):
                            os.remove(debug_path)
                    except Exception as e:
                        print(f"   - Lỗi xóa debug file {debug_path}: {e}")
                
                deleted_preprocessed += 1
            
            # Xóa tất cả preprocessed ballots trong database
            preprocessed_ballots.delete()
            print(f"   - Đã xóa {deleted_preprocessed} preprocessed ballots")
            
            # 5. Xóa BallotSelection
            ballot_selections = BallotSelection.objects.filter(ballot__poll_id=poll_id)
            selections_count = ballot_selections.count()
            
            print(f"\n5. Xóa BallotSelection:")
            print(f"   - Số ballot selections: {selections_count}")
            
            if selections_count > 0:
                ballot_selections.delete()
                print(f"   - Đã xóa {selections_count} ballot selections")
            else:
                print(f"   - Không có ballot selections nào để xóa")
            
            # 6. Xử lý xóa AIModelResult
            ai_results = AIModelResult.objects.filter(ballot__poll_id=poll_id)
            ai_results_count = ai_results.count()
            
            print(f"\n6. Xóa AIModelResult:")
            print(f"   - Số AI model results: {ai_results_count}")
            
            if ai_results_count > 0:
                ai_results.delete()
                print(f"   - Đã xóa {ai_results_count} AI model results")
            else:
                print(f"   - Không có AI model results nào để xóa")
            
            print(f"\n✅ Hoàn thành cleanup cho Poll {poll_id}!")
            print(f"Tóm tắt:")
            print(f"- Ballots được xử lý: {total_ballots}")
            print(f"- Ballot images đã xóa: {deleted_images}")
            print(f"- Ballots đã reset (counting_status, checking_status, input_by, process_status, checking_locked_by, checking_locked_at): {updated_ballots}")
            print(f"- Ballot cells đã xóa: {total_cells_deleted}")
            print(f"- Preprocessed ballots đã xóa: {deleted_preprocessed}")
            print(f"- Ballot selections đã xóa: {selections_count}")
            print(f"- AI model results đã xóa: {ai_results_count}")
            
    except Exception as e:
        print(f"❌ Lỗi trong quá trình cleanup: {e}")
        raise


def confirm_action(poll_id):
    """Xác nhận trước khi thực hiện"""
    print(f"⚠️  CẢNH BÁO: Script này sẽ xóa VĨNH VIỄN dữ liệu sau cho Poll {poll_id}:")
    print("   - Tất cả ballot_image (file ảnh gốc)")
    print("   - Reset counting_status=pending, checking_status=NEW, input_by=null, process_status=no_upload, checking_locked_by=null, checking_locked_at=null")
    print("   - Tất cả ballot_cell (ô đã cắt)")
    print("   - Tất cả preprocessed_ballot (dữ liệu xử lý)")
    print("   - Tất cả ballot_selection (lựa chọn ứng viên)")
    print("   - Tất cả ai_model_result (kết quả AI)")
    print()
    
    response = input("Bạn có chắc chắn muốn tiếp tục? (yes/no): ").strip().lower()
    
    if response in ['yes', 'y', 'có']:
        return True
    else:
        print("Đã hủy thao tác.")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup dữ liệu cho một poll")
    parser.add_argument(
        "--poll-id",
        type=int,
        default=None,
        help="Poll ID cần cleanup. Nếu bỏ trống sẽ dùng POLL_ID_TO_CLEANUP trong file; nếu biến này là None thì tự lấy poll hiện tại",
    )
    args = parser.parse_args()

    if args.poll_id is not None:
        poll_id = args.poll_id
    elif POLL_ID_TO_CLEANUP is not None:
        poll_id = POLL_ID_TO_CLEANUP
    else:
        poll_id = get_current_poll_id()

    if poll_id is None:
        print("❌ Không tìm thấy poll hiện tại để cleanup (database chưa có dữ liệu poll/ballot).")
        sys.exit(1)

    print(f"🧹 Cleanup Script for Poll {poll_id}")
    print("=" * 50)

    if confirm_action(poll_id):
        cleanup_poll(poll_id)
    else:
        sys.exit(0)
