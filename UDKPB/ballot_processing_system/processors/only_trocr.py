# only_trocr.py - Hệ thống xử lý phiếu bầu chỉ dùng TrOCR
import os
import shutil
import argparse
import json
from typing import List, Dict
from datetime import datetime

# Import các module tự viết
from core.tien_xu_ly import xu_ly_phieu_bau
from core.trocr import doc_ten_tu_anh

class PhieuBauTrOCRProcessor:
    """
    Lớp xử lý phiếu bầu chỉ sử dụng TrOCR
    """
    
    def __init__(self):
        """
        Khởi tạo processor chỉ với TrOCR
        """
        pass
    
    def phan_tich_ky_tu_cho_dau_x(self, text: str) -> Dict:
        """
        Phân tích đơn giản: chỉ phân biệt TRỐNG vs CÓ DẤU X
        
        Args:
            text: Text được nhận dạng từ TrOCR
            
        Returns:
            Dict chứa kết quả phân tích
        """
        if not text or text.strip() == '':
            return {
                'co_dau_x': False, 
                'ly_do': 'trang_thai_trong', 
                'diem_so': 0,
                'loai': 'TRỐNG'
            }
        
        text_clean = text.strip().upper()
        
        # Tính điểm dựa trên độ giống với ký tự X
        diem_so = 0
        ly_do_list = []
        
        # 1. Kiểm tra ký tự trực tiếp giống X
        if text_clean == 'X':
            diem_so += 10
            ly_do_list.append("chinh_xac_X")
        elif 'X' in text_clean:
            diem_so += 8
            ly_do_list.append("chua_X")
        
        # 2. Kiểm tra các ký hiệu tương tự X
        ky_hieu_x = ['×', '✗', '✘', 'XX']
        for ky_hieu in ky_hieu_x:
            if ky_hieu in text_clean:
                diem_so += 9
                ly_do_list.append(f"ky_hieu_X({ky_hieu})")
                break
        
        # 3. Kiểm tra các ký tự có thể từ nét vẽ X
        # X có thể bị nhận nhầm thành các ký tự này
        ky_tu_tuong_tu_x = {
            'V': 5,    # Nửa dưới của X
            'Y': 4,    # Tương tự X nhưng có đuôi
            '/': 3,    # Nét chéo của X  
            '\\': 3,   # Nét chéo ngược của X
            '+': 6,    # Giao nhau giống X
            '*': 7,    # Nhiều nét giao nhau
            'K': 4,    # Có nét chéo
            'N': 3,    # Có nét chéo
            'Z': 3,    # Có nét chéo
        }
        
        for ky_tu, diem in ky_tu_tuong_tu_x.items():
            if text_clean == ky_tu:  # Chỉ so sánh chính xác
                diem_so += diem
                ly_do_list.append(f"tuong_tu_X({ky_tu})")
                break
        
        # 4. Kiểm tra độ dài - X thường ngắn
        if len(text_clean) == 1:
            diem_so += 2  # Ký tự đơn có điểm thêm
            ly_do_list.append("ky_tu_don")
        elif len(text_clean) == 2 and 'X' in text_clean:
            diem_so += 1  # XX hoặc X kết hợp
            ly_do_list.append("2_ky_tu_co_X")
        elif len(text_clean) > 3:
            diem_so -= 5  # Text dài khó là X
            ly_do_list.append("text_dai")
        
        # 5. Loại trừ chắc chắn KHÔNG phải X
        khong_phai_x = [
            # Số
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
            # Chữ cái đơn rõ ràng không phải X  
            'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'M', 'O', 'P', 'Q', 'R', 'S', 'U', 'W',
            # Từ thông dụng
            'THE', 'AND', 'OR', 'NOT', 'YES', 'NO', 'OK'
        ]
        
        if text_clean in khong_phai_x:
            diem_so = -10  # Chắc chắn không phải X
            ly_do_list = [f"khong_phai_X({text_clean})"]
        
        # 6. Kết luận
        co_dau_x = diem_so >= 3  # Ngưỡng thấp để nhận diện X
        loai = 'CÓ DẤU X' if co_dau_x else 'TRỐNG'
        
        return {
            'co_dau_x': co_dau_x,
            'diem_so': diem_so,
            'ly_do': ' + '.join(ly_do_list) if ly_do_list else 'khong_nhan_dien',
            'text_phan_tich': text_clean,
            'loai': loai
        }

    def kiem_tra_dau_x_bang_trocr(self, duong_dan_anh: str) -> Dict:
        """
        Kiểm tra ảnh đồng ý/không đồng ý: chỉ có 2 trạng thái TRỐNG hoặc CÓ DẤU X
        
        Args:
            duong_dan_anh: Đường dẫn đến ảnh
            
        Returns:
            Dict chứa thông tin về dấu X
        """
        try:
            # Sử dụng TrOCR để đọc text trong ảnh
            text = doc_ten_tu_anh(duong_dan_anh)
            
            # Phân tích đơn giản: TRỐNG vs CÓ X
            phan_tich = self.phan_tich_ky_tu_cho_dau_x(text)
            
            # Xác định confidence dựa trên điểm số
            if phan_tich['diem_so'] >= 8:
                confidence = 'cao'  # Chắc chắn có X
            elif phan_tich['diem_so'] >= 3:
                confidence = 'trung_binh'  # Có thể có X
            elif phan_tich['diem_so'] <= -5:
                confidence = 'cao_khong_co'  # Chắc chắn không có X
            else:
                confidence = 'thap'  # Không rõ ràng
            
            return {
                'co_dau_x': phan_tich['co_dau_x'],
                'text_nhan_dien': text if text else '',
                'confidence': confidence,
                'diem_so': phan_tich['diem_so'],
                'ly_do': phan_tich['ly_do'],
                'loai': phan_tich['loai'],
                'loi': None
            }
            
        except Exception as e:
            return {
                'co_dau_x': False,
                'text_nhan_dien': '',
                'confidence': 'loi',
                'diem_so': 0,
                'ly_do': 'loi_xu_ly',
                'loai': 'LỖI',
                'loi': str(e)
            }
    
    def xu_ly_mot_dong(self, dong_anh: List[Dict], so_dong: int) -> Dict:
        """
        Xử lý một dòng gồm 4 ảnh: STT, Họ tên, Đồng ý, Không đồng ý
        
        Args:
            dong_anh: List chứa 4 dict với thông tin ảnh
            so_dong: Số thứ tự dòng (bắt đầu từ 1)
            
        Returns:
            Dict chứa kết quả xử lý
        """
        ket_qua = {
            'stt': so_dong,  # Sử dụng số dòng
            'ho_ten': '',
            'dong_y': False,
            'khong_dong_y': False,
            'chi_tiet': {
                'ho_ten_ocr': '',
                'dong_y_trocr': {},
                'khong_dong_y_trocr': {},
                'loi': []
            }
        }
        
        # Xử lý từng ô
        for o in dong_anh:
            loai = o['loai']
            duong_dan = o['duong_dan']
            
            try:
                if loai == 'stt':
                    # Bỏ qua STT vì đã dùng số dòng
                    pass
                    
                elif loai == 'hoten':
                    # OCR cho họ tên
                    ten_text = doc_ten_tu_anh(duong_dan)
                    ket_qua['ho_ten'] = ten_text if ten_text else ''
                    ket_qua['chi_tiet']['ho_ten_ocr'] = ten_text
                    
                elif loai == 'dongy':
                    # TrOCR cho ô đồng ý
                    trocr_result = self.kiem_tra_dau_x_bang_trocr(duong_dan)
                    ket_qua['dong_y'] = trocr_result['co_dau_x']
                    ket_qua['chi_tiet']['dong_y_trocr'] = trocr_result
                    
                elif loai == 'khongdongy':
                    # TrOCR cho ô không đồng ý
                    trocr_result = self.kiem_tra_dau_x_bang_trocr(duong_dan)
                    ket_qua['khong_dong_y'] = trocr_result['co_dau_x']
                    ket_qua['chi_tiet']['khong_dong_y_trocr'] = trocr_result
                    
            except Exception as e:
                loi_msg = f"Lỗi xử lý {loai}: {str(e)}"
                ket_qua['chi_tiet']['loi'].append(loi_msg)
                print(f"[ERROR] {loi_msg}")
        
        return ket_qua
    
    def xu_ly_phieu_bau_hoan_chinh(self, 
                                   duong_dan_anh: str,
                                   thu_muc_temp: str = "results/ket_qua_only_trocr/temp_processing") -> List[Dict]:
        """
        Xử lý hoàn chỉnh một phiếu bầu
        
        Args:
            duong_dan_anh: Đường dẫn đến ảnh phiếu bầu gốc
            thu_muc_temp: Thư mục tạm để lưu ảnh đã cắt
            
        Returns:
            List các kết quả xử lý cho từng dòng
        """
        # Bước 1: Tiền xử lý và cắt ảnh
        ma_tran_anh = xu_ly_phieu_bau(duong_dan_anh, thu_muc_temp)
        
        if not ma_tran_anh:
            print("  [ERROR] Không thể tiền xử lý ảnh")
            return []
        
        # Bước 2: Xử lý từng dòng với TrOCR
        ket_qua_tong = []
        
        for i, dong_anh in enumerate(ma_tran_anh, 1):
            ket_qua_dong = self.xu_ly_mot_dong(dong_anh, i)
            ket_qua_dong['so_dong'] = i
            ket_qua_tong.append(ket_qua_dong)
        
        # Bước 3: Tổng hợp kết quả
        self.in_ket_qua_tong_hop(ket_qua_tong)
        
        return ket_qua_tong
    
    def in_ket_qua_tong_hop(self, ket_qua_tong: List[Dict]):
        """
        In kết quả tổng hợp
        """
        print(f"\n{'='*70}")
        print(f"KẾT QUẢ XỬ LÝ PHIẾU BẦU - CHỈ DÙNG TrOCR")
        print(f"{'='*70}")
        
        tong_dong = len(ket_qua_tong)
        so_dong_y = sum(1 for kq in ket_qua_tong if kq['dong_y'])
        so_khong_dong_y = sum(1 for kq in ket_qua_tong if kq['khong_dong_y'])
        so_khong_chon = sum(1 for kq in ket_qua_tong if not kq['dong_y'] and not kq['khong_dong_y'])
        so_chon_ca_hai = sum(1 for kq in ket_qua_tong if kq['dong_y'] and kq['khong_dong_y'])
        
        print(f"Tổng số ứng viên: {tong_dong}")
        print(f"Đồng ý: {so_dong_y}")
        print(f"Không đồng ý: {so_khong_dong_y}")
        print(f"Không chọn: {so_khong_chon}")
        print(f"Chọn cả hai (lỗi): {so_chon_ca_hai}")
        
        print(f"\nCHI TIẾT TỪNG ỨNG VIÊN:")
        print("-" * 70)
        
        for kq in ket_qua_tong:
            trang_thai = "❌ Lỗi (chọn cả hai)" if (kq['dong_y'] and kq['khong_dong_y']) else \
                        "✅ Đồng ý" if kq['dong_y'] else \
                        "❌ Không đồng ý" if kq['khong_dong_y'] else \
                        "⚪ Không chọn"
            
            # Thông tin về trạng thái ô đồng ý và không đồng ý
            dong_y_info = kq['chi_tiet']['dong_y_trocr']
            khong_dong_y_info = kq['chi_tiet']['khong_dong_y_trocr']
            
            dong_y_loai = dong_y_info.get('loai', 'N/A')
            khong_dong_y_loai = khong_dong_y_info.get('loai', 'N/A')
            
            dong_y_diem = dong_y_info.get('diem_so', 0)
            khong_dong_y_diem = khong_dong_y_info.get('diem_so', 0)
            
            print(f"Dòng {kq['so_dong']:2d} | STT: {kq['stt']:3d} | {kq['ho_ten']:25s} | {trang_thai}")
            print(f"       | Đồng ý: {dong_y_loai}({dong_y_diem}) | Không đồng ý: {khong_dong_y_loai}({khong_dong_y_diem})")
            
            # Chỉ hiển thị text nếu không phải trạng thái TRỐNG
            dong_y_text = dong_y_info.get('text_nhan_dien', '') if dong_y_loai != 'TRỐNG' else ''
            khong_dong_y_text = khong_dong_y_info.get('text_nhan_dien', '') if khong_dong_y_loai != 'TRỐNG' else ''
            
            if dong_y_text or khong_dong_y_text:
                print(f"       | Text: Đồng ý='{dong_y_text}' | Không đồng ý='{khong_dong_y_text}'")
    
    def xu_ly_nhieu_phieu_bau(self, 
                              thu_muc_anh=None,
                              thu_muc_output: str = "results/ket_qua_only_trocr") -> Dict:
        """
        Xử lý nhiều phiếu bầu trong các thư mục (hỗ trợ ballot/data1, ballot/data2)
        
        Args:
            thu_muc_anh: Thư mục hoặc danh sách thư mục chứa ảnh phiếu bầu (mặc định: ["ballot/data1", "ballot/data2"])
            thu_muc_output: Thư mục lưu kết quả (mặc định: results/ket_qua_only_trocr)
            
        Returns:
            Dict chứa kết quả tổng hợp
        """
        # Xử lý tham số đầu vào
        if thu_muc_anh is None:
            thu_muc_anh = ["ballot/data1", "ballot/data2"]  # Mặc định xử lý cả 2 thư mục
        elif isinstance(thu_muc_anh, str):
            thu_muc_anh = [thu_muc_anh]  # Chuyển string thành list
        
        # Tạo thư mục output chính
        os.makedirs(thu_muc_output, exist_ok=True)
        
        ket_qua_tong_hop = {}
        total_files = 0
        total_success = 0
        
        for input_dir in thu_muc_anh:
            if not os.path.exists(input_dir):
                print(f"⚠️ Thư mục {input_dir} không tồn tại, bỏ qua...")
                continue
            
            # Tạo thư mục con cho từng input_dir
            sub_output_dir = os.path.join(thu_muc_output, f"ket_qua_{os.path.basename(input_dir)}")
            os.makedirs(sub_output_dir, exist_ok=True)
            
            # Lấy danh sách ảnh
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
            image_files = []
            
            for filename in os.listdir(input_dir):
                if any(filename.lower().endswith(ext) for ext in image_extensions):
                    image_files.append(os.path.join(input_dir, filename))
            
            if not image_files:
                print(f"❌ Không tìm thấy ảnh nào trong {input_dir}!")
                continue
            
            total_files += len(image_files)
            
            # Tạo thư mục temp cho thư mục này
            thu_muc_temp = os.path.join(sub_output_dir, "temp_processing")
            os.makedirs(thu_muc_temp, exist_ok=True)
            
            success_count = 0
            
            for i, image_path in enumerate(image_files, 1):
                try:
                    ten_file = os.path.splitext(os.path.basename(image_path))[0]
                    
                    # Xử lý phiếu bầu
                    ket_qua = self.xu_ly_phieu_bau_hoan_chinh(image_path, thu_muc_temp)
                    ket_qua_tong_hop[image_path] = ket_qua
                    
                    # Lưu kết quả chi tiết riêng cho từng phiếu
                    self.luu_ket_qua_json(ket_qua, os.path.join(sub_output_dir, f"{ten_file}_result.json"))
                    
                    success_count += 1
                    total_success += 1
                    
                except Exception as e:
                    print(f"❌ Lỗi xử lý {image_path}: {str(e)}")
                    ket_qua_tong_hop[image_path] = []
            
            
            # Xóa thư mục temp sau khi hoàn thành thư mục này
            try:
                if os.path.exists(thu_muc_temp):
                    shutil.rmtree(thu_muc_temp)
            except Exception:
                pass
        
        # Tạo file tổng hợp
        tong_hop_don_gian = self.tao_tong_hop_don_gian(ket_qua_tong_hop)
        self.luu_ket_qua_json(tong_hop_don_gian, os.path.join(thu_muc_output, "tong_hop_ket_qua.json"))
        
        # In thông tin tổng kết
        print(f"\n{'='*70}")
        print(f"TỔNG KẾT QUẢ XỬ LÝ BATCH - CHỈ DÙNG TrOCR")
        print(f"{'='*70}")
        print(f"Tổng số phiếu: {tong_hop_don_gian['tong_so_phieu_bau']}")
        print(f"Phiếu hợp lệ: {tong_hop_don_gian['tong_so_phieu_hop_le']}")
        print(f"Phiếu lỗi: {tong_hop_don_gian['tong_so_phieu_loi']}")
        print(f"Đã xử lý: {total_success}/{total_files} ảnh từ {len(thu_muc_anh)} thư mục")
        
        if tong_hop_don_gian['danh_sach_phieu_loi']:
            print(f"\nDanh sách phiếu lỗi:")
            for phieu_loi in tong_hop_don_gian['danh_sach_phieu_loi']:
                print(f"  - {phieu_loi}")
        
        print(f"\nTop 5 ứng viên được đồng ý nhiều nhất:")
        for i, ung_vien in enumerate(tong_hop_don_gian['ket_qua_binh_chon'][:5], 1):
            print(f"  {i}. {ung_vien['ho_ten']}: {ung_vien['so_luot_dong_y']} lượt")
        
        return ket_qua_tong_hop
    
    def tao_tong_hop_don_gian(self, ket_qua_tong_hop: Dict) -> Dict:
        """
        Tạo file tổng hợp đơn giản chỉ có tên và số lượng đồng ý
        
        Args:
            ket_qua_tong_hop: Kết quả chi tiết từ tất cả phiếu bầu
            
        Returns:
            Dict chứa thống kê đơn giản
        """
        # Đếm số lượt đồng ý cho từng người
        dem_dong_y = {}
        tong_so_phieu_hop_le = 0
        danh_sach_phieu_loi = []
        
        for file_path, ket_qua_phieu in ket_qua_tong_hop.items():
            ten_file = os.path.basename(file_path)
            
            if ket_qua_phieu:  # Nếu có kết quả
                # Kiểm tra xem phiếu có lỗi không
                phieu_co_loi = False
                
                for ung_vien in ket_qua_phieu:
                    dong_y = ung_vien['dong_y']
                    khong_dong_y = ung_vien['khong_dong_y']
                    
                    # Kiểm tra lỗi: chọn cả hai hoặc không chọn gì
                    if (dong_y and khong_dong_y) or (not dong_y and not khong_dong_y):
                        phieu_co_loi = True
                        break
                
                if phieu_co_loi:
                    # Phiếu lỗi - không tính vào kết quả
                    danh_sach_phieu_loi.append(ten_file)
                else:
                    # Phiếu hợp lệ - tính vào kết quả
                    tong_so_phieu_hop_le += 1
                    for ung_vien in ket_qua_phieu:
                        ten = ung_vien['ho_ten']
                        dong_y = ung_vien['dong_y']
                        
                        if ten and ten.strip():  # Nếu có tên
                            if ten not in dem_dong_y:
                                dem_dong_y[ten] = 0
                            if dong_y:
                                dem_dong_y[ten] += 1
        
        # Sắp xếp theo số lượt đồng ý giảm dần
        danh_sach_ket_qua = []
        for ten, so_dong_y in sorted(dem_dong_y.items(), key=lambda x: x[1], reverse=True):
            danh_sach_ket_qua.append({
                'ho_ten': ten,
                'so_luot_dong_y': so_dong_y
            })
        
        return {
            'tong_so_phieu_bau': len(ket_qua_tong_hop),
            'tong_so_phieu_hop_le': tong_so_phieu_hop_le,
            'tong_so_phieu_loi': len(danh_sach_phieu_loi),
            'danh_sach_phieu_loi': danh_sach_phieu_loi,
            'tong_so_ung_vien': len(dem_dong_y),
            'ket_qua_binh_chon': danh_sach_ket_qua,
            'thoi_gian_xu_ly': self.get_current_time(),
            'phuong_phap': 'TrOCR only - không dùng YOLO'
        }
    
    def get_current_time(self) -> str:
        """
        Lấy thời gian hiện tại
        """
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def luu_ket_qua_json(self, data, file_path: str):
        """
        Lưu kết quả ra file JSON
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def main():
    """
    Hàm main để test hệ thống
    """
    parser = argparse.ArgumentParser(description="Xử lý phiếu bầu chỉ với TrOCR")
    parser.add_argument("--input", default=None, 
                       help="Thư mục hoặc danh sách thư mục chứa ảnh phiếu bầu (mặc định: ballot/data1,ballot/data2)")
    parser.add_argument("--output", default="results/ket_qua_only_trocr",
                       help="Thư mục lưu kết quả (mặc định: results/ket_qua_only_trocr)")
    parser.add_argument("--single", type=str, 
                       help="Xử lý một ảnh cụ thể")
    
    args = parser.parse_args()
    
    # Xử lý tham số input
    if args.input:
        if ',' in args.input:
            input_dirs = [dir.strip() for dir in args.input.split(',')]
        else:
            input_dirs = args.input
    else:
        input_dirs = None  # Sẽ dùng mặc định ["ballot/data1", "ballot/data2"]
    
    # Khởi tạo processor
    processor = PhieuBauTrOCRProcessor()
    
    if args.single:
        # Xử lý một ảnh
        if os.path.exists(args.single):
            ket_qua = processor.xu_ly_phieu_bau_hoan_chinh(args.single)
        else:
            print(f"[ERROR] File không tồn tại: {args.single}")
    else:
        # Xử lý batch
        ket_qua = processor.xu_ly_nhieu_phieu_bau(input_dirs, args.output)

if __name__ == "__main__":
    main()
