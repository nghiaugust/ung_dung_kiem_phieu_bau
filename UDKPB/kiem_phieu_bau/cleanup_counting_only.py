#!/usr/bin/env python
"""
Script để xóa CHỈ dữ liệu kiểm phiếu cho một poll:
- Reset counting_status = pending, counting_error = null
- Xóa tất cả BallotSelection
- Xóa tất cả AIModelResult

KHÔNG XÓA:
- ballot_image (giữ nguyên ảnh đã upload)
- ballot_cell (giữ nguyên ô đã cắt)
- preprocessed_ballot (giữ nguyên dữ liệu xử lý)
- process_status (giữ nguyên là completed)

Sử dụng script này khi bạn muốn kiểm phiếu lại mà KHÔNG cần upload và preprocess lại.
"""

import os
import sys
import django
from django.conf import settings

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiem_phieu_bau.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from ballot.models import Ballot, BallotSelection
from counting.models import AIModelResult
from django.db import transaction


def cleanup_counting_data(poll_id):
    """
    Xóa CHỈ dữ liệu kiểm phiếu cho một poll:
    1. Reset counting_status = pending, counting_error = null
    2. Xóa tất cả BallotSelection
    3. Xóa tất cả AIModelResult
    
    Args:
        poll_id: ID của poll cần cleanup
    """
    
    print(f"Bắt đầu cleanup dữ liệu KIỂM PHIẾU cho Poll {poll_id}")
    
    try:
        with transaction.atomic():
            # Lấy tất cả ballot của poll
            ballots = Ballot.objects.filter(poll_id=poll_id)
            total_ballots = ballots.count()
            
            print(f"Tìm thấy {total_ballots} ballots trong poll {poll_id}")
            
            if total_ballots == 0:
                print("Không có ballot nào được tìm thấy!")
                return
            
            # 1. Reset counting_status và counting_error
            print(f"\n1. Reset counting_status và counting_error:")
            
            updated_ballots = 0
            for ballot in ballots:
                # Chỉ reset các trường liên quan đến counting
                # GIỮ NGUYÊN: process_status, ballot_image, checking_status, input_by
                ballot.counting_status = 'pending'
                ballot.counting_error = None
                ballot.save(update_fields=['counting_status', 'counting_error'])
                updated_ballots += 1
            
            print(f"   - Đã reset {updated_ballots} ballots (counting_status=pending, counting_error=null)")
            
            # 2. Xóa BallotSelection
            ballot_selections = BallotSelection.objects.filter(ballot__poll_id=poll_id)
            selections_count = ballot_selections.count()
            
            print(f"\n2. Xóa BallotSelection:")
            print(f"   - Số ballot selections: {selections_count}")
            
            if selections_count > 0:
                ballot_selections.delete()
                print(f"   - Đã xóa {selections_count} ballot selections")
            else:
                print(f"   - Không có ballot selections nào để xóa")
            
            # 3. Xóa AIModelResult
            ai_results = AIModelResult.objects.filter(ballot__poll_id=poll_id)
            ai_results_count = ai_results.count()
            
            print(f"\n3. Xóa AIModelResult:")
            print(f"   - Số AI model results: {ai_results_count}")
            
            if ai_results_count > 0:
                ai_results.delete()
                print(f"   - Đã xóa {ai_results_count} AI model results")
            else:
                print(f"   - Không có AI model results nào để xóa")
            
            print(f"\n✅ Hoàn thành cleanup KIỂM PHIẾU cho Poll {poll_id}!")
            print(f"\nTóm tắt:")
            print(f"- Ballots được xử lý: {total_ballots}")
            print(f"- Ballots đã reset (counting_status, counting_error): {updated_ballots}")
            print(f"- Ballot selections đã xóa: {selections_count}")
            print(f"- AI model results đã xóa: {ai_results_count}")
            print(f"\n📌 Lưu ý:")
            print(f"- Ballot images VẪN CÒN (không bị xóa)")
            print(f"- Ballot cells VẪN CÒN (không bị xóa)")
            print(f"- Preprocessed ballots VẪN CÒN (không bị xóa)")
            print(f"- Process status VẪN LÀ 'completed' (không bị reset)")
            print(f"\n🚀 Bạn có thể trigger lại counting ngay bây giờ!")
            
    except Exception as e:
        print(f"❌ Lỗi trong quá trình cleanup: {e}")
        raise


def confirm_action(poll_id):
    """Xác nhận trước khi thực hiện"""
    print(f"⚠️  CẢNH BÁO: Script này sẽ xóa dữ liệu KIỂM PHIẾU cho Poll {poll_id}:")
    print("   ✅ ĐƯỢC XÓA:")
    print("      - counting_status → pending")
    print("      - counting_error → null")
    print("      - Tất cả BallotSelection (lựa chọn ứng viên)")
    print("      - Tất cả AIModelResult (kết quả AI)")
    print()
    print("   ❌ KHÔNG XÓA (giữ nguyên):")
    print("      - ballot_image (ảnh đã upload)")
    print("      - ballot_cell (ô đã cắt)")
    print("      - preprocessed_ballot (dữ liệu xử lý)")
    print("      - process_status (vẫn là completed)")
    print("      - checking_status (không thay đổi)")
    print("      - input_by (không thay đổi)")
    print()
    print("   💡 Phù hợp khi: Bạn muốn kiểm phiếu lại mà KHÔNG cần upload lại ảnh")
    print()
    
    response = input("Bạn có chắc chắn muốn tiếp tục? (yes/no): ").strip().lower()
    
    if response in ['yes', 'y', 'có']:
        return True
    else:
        print("Đã hủy thao tác.")
        return False


if __name__ == "__main__":
    # Thay đổi poll_id ở đây
    POLL_ID = 103  # <-- THAY ĐỔI POLL ID TẠI ĐÂY
    
    print("🧹 Cleanup Counting Data Only")
    print("=" * 50)
    print(f"Poll ID: {POLL_ID}")
    print("=" * 50)
    
    if confirm_action(POLL_ID):
        cleanup_counting_data(POLL_ID)
    else:
        sys.exit(0)
