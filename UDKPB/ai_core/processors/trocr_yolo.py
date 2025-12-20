# trocr_yolo.py - Hệ thống tích hợp xử lý phiếu bầu
import os
import shutil
import argparse
import json
from typing import List, Dict
from datetime import datetime

# Import các module tự xây dựng
from core.tien_xu_ly import xu_ly_phieu_bau
from core.trocr import doc_ten_tu_anh

# Import YOLO
try:
    from ultralytics import YOLO
except ImportError:
    print("[WARNING] Chưa cài ultralytics. Sẽ chỉ sử dụng TrOCR.")
    YOLO = None

class PhieuBauProcessor:
    """
    Lớp xử lý phiếu bầu tích hợp TrOCR và YOLO
    """
    
    def __init__(self, 
                 yolo_weights_path: str = "models/best.pt"):
        """
        Khởi tạo processor
        
        Args:
            yolo_weights_path: Đường dẫn đến weights YOLO
        """
        
        # Load YOLO model
        self.yolo_model = None
        if YOLO and os.path.exists(yolo_weights_path):
            try:
                self.yolo_model = YOLO(yolo_weights_path)
            except Exception as e:
                print(f"[WARNING] Không thể load YOLO model: {e}")
        else:
            print("[WARNING] YOLO model không khả dụng")
    
    def kiem_tra_dau_x(self, duong_dan_anh: str) -> Dict:
        """
        Kiểm tra có dấu X trong ảnh không
        Phân biệt x_mark (dấu X hợp lệ) và x_cancelled (dấu X bị gạch bỏ)
        
        Args:
            duong_dan_anh: Đường dẫn đến ảnh
            
        Returns:
            Dict chứa thông tin về dấu X
        """
        if not self.yolo_model:
            return {
                'co_dau_x': False,
                'so_luong_x_mark': 0,
                'so_luong_x_cancelled': 0,
                'confidence_x_mark': [],
                'confidence_x_cancelled': [],
                'chi_tiet_detection': [],
                'loi': 'YOLO model không khả dụng'
            }
        
        try:
            # Predict với YOLO
            results = self.yolo_model.predict(
                source=duong_dan_anh,
                save=False,
                verbose=False
            )
            
            result = results[0]
            
            # Khởi tạo các biến đếm
            so_luong_x_mark = 0
            so_luong_x_cancelled = 0
            confidence_x_mark = []
            confidence_x_cancelled = []
            chi_tiet_detection = []
            
            if result.boxes is not None and len(result.boxes) > 0:
                # Lấy thông tin boxes, classes và confidences
                boxes = result.boxes.xyxy.cpu().numpy()  # Tọa độ boxes
                classes = result.boxes.cls.cpu().numpy()  # Class IDs
                confidences = result.boxes.conf.cpu().numpy()  # Confidence scores
                
                # Lấy tên class từ model
                class_names = result.names  # Dict: {0: 'x_mark', 1: 'x_cancelled', ...}
                
                for i, (box, cls_id, conf) in enumerate(zip(boxes, classes, confidences)):
                    cls_name = class_names[int(cls_id)]
                    
                    # Lưu chi tiết detection
                    detection_info = {
                        'class': cls_name,
                        'confidence': float(conf),
                        'bbox': box.tolist()
                    }
                    chi_tiet_detection.append(detection_info)
                    
                    # Phân loại theo class
                    if cls_name == 'x_mark':
                        so_luong_x_mark += 1
                        confidence_x_mark.append(float(conf))
                    elif cls_name == 'x_cancelled':
                        so_luong_x_cancelled += 1
                        confidence_x_cancelled.append(float(conf))
            
            # Xác định có dấu X hợp lệ hay không
            # Chỉ tính x_mark, bỏ qua x_cancelled
            co_dau_x_hop_le = so_luong_x_mark > 0
            
            return {
                'co_dau_x': co_dau_x_hop_le,
                'so_luong_x_mark': so_luong_x_mark,
                'so_luong_x_cancelled': so_luong_x_cancelled,
                'confidence_x_mark': confidence_x_mark,
                'confidence_x_cancelled': confidence_x_cancelled,
                'chi_tiet_detection': chi_tiet_detection,
                'loi': None
            }
                
        except Exception as e:
            return {
                'co_dau_x': False,
                'so_luong_x_mark': 0,
                'so_luong_x_cancelled': 0,
                'confidence_x_mark': [],
                'confidence_x_cancelled': [],
                'chi_tiet_detection': [],
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
            'stt': so_dong,  # Sử dụng số dòng thay vì OCR
            'ho_ten': '',
            'dong_y': False,
            'khong_dong_y': False,
            'chi_tiet': {
                # 'stt_ocr': '',  # Comment tạm thời
                'ho_ten_ocr': '',
                'dong_y_yolo': {},
                'khong_dong_y_yolo': {},
                'loi': []
            }
        }
        
        # Xử lý từng ô
        for o in dong_anh:
            loai = o['loai']
            duong_dan = o['duong_dan']
            
            try:
                if loai == 'stt':
                    # Comment tạm thời - OCR cho STT (chỉ để ghi log, không dùng làm kết quả)
                    # stt_text = doc_ten_tu_anh(duong_dan)
                    # ket_qua['chi_tiet']['stt_ocr'] = stt_text
                    # STT đã được set theo số dòng ở trên
                    pass
                    
                elif loai == 'hoten':
                    # OCR cho họ tên
                    ten_text = doc_ten_tu_anh(duong_dan)
                    ket_qua['ho_ten'] = ten_text if ten_text else ''
                    ket_qua['chi_tiet']['ho_ten_ocr'] = ten_text
                    
                elif loai == 'dongy':
                    # YOLO cho ô đồng ý
                    yolo_result = self.kiem_tra_dau_x(duong_dan)
                    ket_qua['dong_y'] = yolo_result['co_dau_x']
                    ket_qua['chi_tiet']['dong_y_yolo'] = yolo_result
                    
                elif loai == 'khongdongy':
                    # YOLO cho ô không đồng ý
                    yolo_result = self.kiem_tra_dau_x(duong_dan)
                    ket_qua['khong_dong_y'] = yolo_result['co_dau_x']
                    ket_qua['chi_tiet']['khong_dong_y_yolo'] = yolo_result
                    
            except Exception as e:
                loi_msg = f"Lỗi xử lý {loai}: {str(e)}"
                ket_qua['chi_tiet']['loi'].append(loi_msg)
                print(f"[ERROR] {loi_msg}")
        
        return ket_qua
    
    def xu_ly_phieu_bau_hoan_chinh(self, 
                                   duong_dan_anh: str,
                                   thu_muc_temp: str = "results/ket_qua_trocr_yolo/temp_processing") -> List[Dict]:
        """
        Xử lý hoàn chỉnh một phiếu bầu
        
        Args:
            duong_dan_anh: Đường dẫn đến ảnh phiếu bầu gốc
            thu_muc_temp: Thư mục tạm để lưu ảnh đã cắt
            
        Returns:
            List các kết quả xử lý cho từng dòng
        """
        # Bước 1: Tiền xử lý và cắt ảnh (auto-detect layout trong xu_ly_phieu_bau)
        ma_tran_anh = xu_ly_phieu_bau(duong_dan_anh, thu_muc_temp)
        
        if not ma_tran_anh:
            print("  [ERROR] Không thể tiền xử lý ảnh")
            return []
        
        # Bước 2: Xử lý từng dòng với TrOCR + YOLO
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
        print(f"\n{'='*60}")
        print(f"KẾT QUẢ XỬ LÝ PHIẾU BẦU")
        print(f"{'='*60}")
        
        tong_dong = len(ket_qua_tong)
        so_dong_y = sum(1 for kq in ket_qua_tong if kq['dong_y'])
        so_khong_dong_y = sum(1 for kq in ket_qua_tong if kq['khong_dong_y'])
        so_khong_chon = sum(1 for kq in ket_qua_tong if not kq['dong_y'] and not kq['khong_dong_y'])
        so_chon_ca_hai = sum(1 for kq in ket_qua_tong if kq['dong_y'] and kq['khong_dong_y'])
        
        # Thống kê x_cancelled
        so_x_cancelled_dong_y = sum(1 for kq in ket_qua_tong 
                                   if kq.get('chi_tiet', {}).get('dong_y_yolo', {}).get('so_luong_x_cancelled', 0) > 0)
        so_x_cancelled_khong_dong_y = sum(1 for kq in ket_qua_tong 
                                         if kq.get('chi_tiet', {}).get('khong_dong_y_yolo', {}).get('so_luong_x_cancelled', 0) > 0)
        
        print(f"Tổng số ứng viên: {tong_dong}")
        print(f"Đồng ý: {so_dong_y}")
        print(f"Không đồng ý: {so_khong_dong_y}")
        print(f"Không chọn: {so_khong_chon}")
        print(f"Chọn cả hai (lỗi): {so_chon_ca_hai}")
        print(f"Có dấu X bị gạch bỏ ở ô đồng ý: {so_x_cancelled_dong_y}")
        print(f"Có dấu X bị gạch bỏ ở ô không đồng ý: {so_x_cancelled_khong_dong_y}")
        
        print(f"\nCHI TIẾT TỪNG ỨNG VIÊN:")
        print("-" * 80)
        
        for kq in ket_qua_tong:
            trang_thai = "❌ Lỗi (chọn cả hai)" if (kq['dong_y'] and kq['khong_dong_y']) else \
                        "✅ Đồng ý" if kq['dong_y'] else \
                        "❌ Không đồng ý" if kq['khong_dong_y'] else \
                        "⚪ Không chọn"
            
            # Thêm thông tin về x_cancelled
            cancelled_info = ""
            dong_y_cancelled = kq.get('chi_tiet', {}).get('dong_y_yolo', {}).get('so_luong_x_cancelled', 0)
            khong_dong_y_cancelled = kq.get('chi_tiet', {}).get('khong_dong_y_yolo', {}).get('so_luong_x_cancelled', 0)
            
            if dong_y_cancelled > 0 or khong_dong_y_cancelled > 0:
                cancelled_info = f" [Gạch bỏ: ĐY:{dong_y_cancelled}, KĐY:{khong_dong_y_cancelled}]"
            
            print(f"Dòng {kq['so_dong']:2d} | STT: {kq['stt']:3d} | {kq['ho_ten']:25s} | {trang_thai}{cancelled_info}")
    
    def xu_ly_nhieu_phieu_bau(self, 
                              thu_muc_anh=None,
                              thu_muc_output: str = "results/ket_qua_trocr_yolo") -> Dict:
        """
        Xử lý nhiều phiếu bầu trong các thư mục (hỗ trợ ballot/data1, ballot/data2)
        
        Args:
            thu_muc_anh: Thư mục hoặc danh sách thư mục chứa ảnh phiếu bầu (mặc định: ["ballot/data1", "ballot/data2"])
            thu_muc_output: Thư mục lưu kết quả
            
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
                    self.luu_ket_qua_json(ket_qua, os.path.join(sub_output_dir, f"{ten_file}.json"))
                    
                    success_count += 1
                    total_success += 1
                    
                except Exception as e:
                    print(f"❌ Lỗi xử lý {image_path}: {str(e)}")
                    ket_qua_tong_hop[image_path] = []
    
            
            # Xóa thư mục temp sau khi hoàn thành thư mục này
            try:
                if os.path.exists(thu_muc_temp):
                    shutil.rmtree(thu_muc_temp)
                # Nếu thư mục cha (sub_output_dir) rỗng thì xoá luôn
                if os.path.exists(sub_output_dir) and not os.listdir(sub_output_dir):
                    os.rmdir(sub_output_dir)
            except Exception:
                pass
        
        # Tạo file tổng hợp
        tong_hop_don_gian = self.tao_tong_hop_don_gian(ket_qua_tong_hop)
        #self.luu_ket_qua_json(tong_hop_don_gian, os.path.join(thu_muc_output, "tong_hop_ket_qua.json"))
        
        # In thông tin tổng kết
        print(f"\n{'='*70}")
        print(f"TỔNG KẾT QUẢ XỬ LÝ BATCH - TrOCR + YOLO")
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
            'phuong_phap': 'TrOCR + YOLO tích hợp'
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
    parser = argparse.ArgumentParser(description="Xử lý phiếu bầu với TrOCR + YOLO")
    parser.add_argument("--input", default=None, help="Thư mục hoặc danh sách thư mục chứa ảnh phiếu bầu (mặc định: ballot/data1,ballot/data2)")
    parser.add_argument("--output", default="results/ket_qua_trocr_yolo", help="Thư mục lưu kết quả")
    parser.add_argument("--weights", default="models/best.pt", help="Đường dẫn YOLO weights")
    parser.add_argument("--single", type=str, help="Xử lý một ảnh cụ thể")
    parser.add_argument("--input_dir", type=str, help="Thư mục chứa ảnh để xử lý batch (ưu tiên nếu truyền)")
    parser.add_argument("--output_dir", type=str, help="Thư mục lưu kết quả batch (ưu tiên nếu truyền)")

    args = parser.parse_args()

    # Ưu tiên nhận input_dir và output_dir nếu có
    if args.input_dir and args.output_dir:
        input_dirs = args.input_dir
        output_dir = args.output_dir
    else:
        # Xử lý tham số input/output cũ
        if args.input:
            if ',' in args.input:
                input_dirs = [dir.strip() for dir in args.input.split(',')]
            else:
                input_dirs = args.input
        else:
            input_dirs = None  # Sẽ dùng mặc định ["ballot/data1", "ballot/data2"]
        output_dir = args.output

    # Khởi tạo processor
    processor = PhieuBauProcessor(yolo_weights_path=args.weights)

    if args.single:
        # Xử lý một ảnh
        if os.path.exists(args.single):
            ket_qua = processor.xu_ly_phieu_bau_hoan_chinh(args.single)
            # Lưu kết quả ra file JSON
            output_dir_single = os.path.join("results/ket_qua_trocr_yolo", "ket_qua_1_anh")
            os.makedirs(output_dir_single, exist_ok=True)
            ten_file = os.path.splitext(os.path.basename(args.single))[0]
            output_path = os.path.join(output_dir_single, f"{ten_file}.json")
            processor.luu_ket_qua_json(ket_qua, output_path)
            print(f"[INFO] Đã lưu kết quả vào: {output_path}")
        else:
            print(f"[ERROR] File không tồn tại: {args.single}")
    else:
        # Xử lý batch
        ket_qua = processor.xu_ly_nhieu_phieu_bau(input_dirs, output_dir)

if __name__ == "__main__":
    main()
