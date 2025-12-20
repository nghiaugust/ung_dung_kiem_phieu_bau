"""
visualize_detection.py - Trực quan hóa kết quả detection của hệ thống AI
Vẽ bounding boxes cho YOLO detection (dấu X) và vùng tên (thủ công)
"""

import cv2
import numpy as np
import os
from typing import List, Dict, Tuple
from ultralytics import YOLO

# Import tiền xử lý
from core.tien_xu_ly import straighten_ballot


# Layout cho data1 (từ file tien_xu_ly.py)
Y_MIN1, Y_MAX1 = 208, 2225
COL_BOUNDARIES1 = [385, 974, 1233, 1481]


class BallotVisualizer:
    """Lớp để trực quan hóa kết quả detection trên phiếu bầu"""
    
    def __init__(self, yolo_weights_path: str = "models/best.pt"):
        """
        Khởi tạo visualizer
        
        Args:
            yolo_weights_path: Đường dẫn đến weights YOLO
        """
        # Load YOLO model
        self.yolo_model = None
        if os.path.exists(yolo_weights_path):
            try:
                self.yolo_model = YOLO(yolo_weights_path)
                print(f"✅ Đã load YOLO model từ: {yolo_weights_path}")
            except Exception as e:
                print(f"❌ Không thể load YOLO model: {e}")
        else:
            print(f"❌ Không tìm thấy YOLO weights: {yolo_weights_path}")
        
    
    def get_name_regions(self) -> List[Tuple[int, int, int, int]]:
        """
        Tính toán bounding boxes cho các vùng tên dựa trên layout data1
        
        Returns:
            List của các tuple (x1, y1, x2, y2) cho 10 vùng tên
        """
        # 11 dòng cao bằng nhau, bỏ header (dòng đầu), lấy 10 dòng
        cell_h = (Y_MAX1 - Y_MIN1) / 11
        name_regions = []
        
        for row in range(1, 11):  # Dòng 1-10 (bỏ dòng 0 - header)
            y1 = int(Y_MIN1 + row * cell_h)
            y2 = int(Y_MIN1 + (row + 1) * cell_h)
            x1 = COL_BOUNDARIES1[0]  # Cột tên
            x2 = COL_BOUNDARIES1[1]
            name_regions.append((x1, y1, x2, y2))
        
        return name_regions
    
    def get_checkbox_regions(self) -> Tuple[List[Tuple[int, int, int, int]], List[Tuple[int, int, int, int]]]:
        """
        Tính toán bounding boxes cho các ô đồng ý và không đồng ý
        
        Returns:
            Tuple of (agree_regions, disagree_regions)
            Mỗi region là tuple (x1, y1, x2, y2)
        """
        cell_h = (Y_MAX1 - Y_MIN1) / 11
        agree_regions = []
        disagree_regions = []
        
        for row in range(1, 11):  # Dòng 1-10
            y1 = int(Y_MIN1 + row * cell_h)
            y2 = int(Y_MIN1 + (row + 1) * cell_h)
            
            # Ô đồng ý
            agree_x1 = COL_BOUNDARIES1[1]
            agree_x2 = COL_BOUNDARIES1[2]
            agree_regions.append((agree_x1, y1, agree_x2, y2))
            
            # Ô không đồng ý
            disagree_x1 = COL_BOUNDARIES1[2]
            disagree_x2 = COL_BOUNDARIES1[3]
            disagree_regions.append((disagree_x1, y1, disagree_x2, y2))
        
        return agree_regions, disagree_regions
    
    def detect_x_marks_in_region(self, image: np.ndarray, region: Tuple[int, int, int, int]) -> List[Dict]:
        """
        Detect dấu X trong một vùng cụ thể
        
        Args:
            image: Ảnh đầu vào
            region: Tuple (x1, y1, x2, y2) của vùng cần detect
            
        Returns:
            List các detection với thông tin class, confidence, bbox
        """
        if self.yolo_model is None:
            return []
        
        x1, y1, x2, y2 = region
        # Crop vùng để detect
        cropped = image[y1:y2, x1:x2]
        
        if cropped.size == 0:
            return []
        
        try:
            # Predict với YOLO
            results = self.yolo_model.predict(
                source=cropped,
                save=False,
                verbose=False
            )
            
            result = results[0]
            detections = []
            
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes.xyxy.cpu().numpy()
                classes = result.boxes.cls.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_names = result.names
                
                for box, cls_id, conf in zip(boxes, classes, confidences):
                    cls_name = class_names[int(cls_id)]
                    
                    # Chuyển tọa độ từ cropped image về tọa độ ảnh gốc
                    abs_box = [
                        int(box[0] + x1),
                        int(box[1] + y1),
                        int(box[2] + x1),
                        int(box[3] + y1)
                    ]
                    
                    detections.append({
                        'class': cls_name,
                        'confidence': float(conf),
                        'bbox': abs_box
                    })
            
            return detections
            
        except Exception as e:
            print(f"❌ Lỗi khi detect trong vùng {region}: {e}")
            return []
    
    
    def draw_detections(self, 
                       image: np.ndarray,
                       agree_detections: List[List[Dict]],
                       disagree_detections: List[List[Dict]]) -> np.ndarray:
        """
        Vẽ bounding boxes YOLO lên ảnh
        """
        output_img = image.copy()
        # Vẽ detections cho ô đồng ý (màu xanh lá)
        for row_idx, detections in enumerate(agree_detections):
            for det in detections:
                bbox = det['bbox']
                cls_name = det['class']
                conf = det['confidence']
                if cls_name == 'x_mark':
                    color = (0, 255, 0)  # Green
                elif cls_name == 'x_cancelled':
                    color = (0, 165, 255)  # Orange
                else:
                    color = (0, 255, 0)
                cv2.rectangle(output_img, 
                            (bbox[0], bbox[1]), 
                            (bbox[2], bbox[3]), 
                            color, 3)
                label = f"{cls_name}: {conf:.2f}"
                text_y = bbox[1] - 10
                (text_w, text_h), baseline = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                )
                cv2.rectangle(output_img,
                            (bbox[0], text_y - text_h - baseline),
                            (bbox[0] + text_w, text_y + baseline),
                            color, -1)
                cv2.putText(output_img, label,
                          (bbox[0], text_y),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        # Vẽ detections cho ô không đồng ý (màu đỏ)
        for row_idx, detections in enumerate(disagree_detections):
            for det in detections:
                bbox = det['bbox']
                cls_name = det['class']
                conf = det['confidence']
                if cls_name == 'x_mark':
                    color = (0, 0, 255)  # Red
                elif cls_name == 'x_cancelled':
                    color = (0, 165, 255)  # Orange
                else:
                    color = (0, 0, 255)
                cv2.rectangle(output_img,
                            (bbox[0], bbox[1]),
                            (bbox[2], bbox[3]),
                            color, 3)
                label = f"{cls_name}: {conf:.2f}"
                text_y = bbox[1] - 10
                (text_w, text_h), baseline = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                )
                cv2.rectangle(output_img,
                            (bbox[0], text_y - text_h - baseline),
                            (bbox[0] + text_w, text_y + baseline),
                            color, -1)
                cv2.putText(output_img, label,
                          (bbox[0], text_y),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return output_img
    
    def process_ballot(self, 
                      image_path: str,
                      output_path: str = None) -> np.ndarray:
        """
        Xử lý phiếu bầu và trực quan hóa kết quả YOLO
        """
        print(f"📸 Đang xử lý: {image_path}")
        # Bước 1: Tiền xử lý - làm phẳng ảnh
        print("  ⚙️ Bước 1: Tiền xử lý...")
        try:
            straightened_img = straighten_ballot(image_path)
            print("  ✅ Đã làm phẳng ảnh")
        except Exception as e:
            print(f"  ❌ Lỗi tiền xử lý: {e}")
            return None
        # Bước 2: Lấy các vùng cần detect
        print("  ⚙️ Bước 2: Xác định vùng detection...")
        agree_regions, disagree_regions = self.get_checkbox_regions()
        print(f"  ✅ Đã xác định {len(agree_regions)} ô đồng ý, {len(disagree_regions)} ô không đồng ý")
        # Bước 3: Detect dấu X trong các ô
        print("  ⚙️ Bước 3: Detect dấu X bằng YOLO...")
        agree_detections = []
        disagree_detections = []
        for i, region in enumerate(agree_regions, 1):
            detections = self.detect_x_marks_in_region(straightened_img, region)
            agree_detections.append(detections)
            if detections:
                print(f"    ✅ Dòng {i} - Đồng ý: Tìm thấy {len(detections)} detection(s)")
        for i, region in enumerate(disagree_regions, 1):
            detections = self.detect_x_marks_in_region(straightened_img, region)
            disagree_detections.append(detections)
            if detections:
                print(f"    ✅ Dòng {i} - Không đồng ý: Tìm thấy {len(detections)} detection(s)")
        # Bước 4: Vẽ bounding boxes
        print("  ⚙️ Bước 4: Vẽ bounding boxes...")
        output_img = self.draw_detections(
            straightened_img,
            agree_detections,
            disagree_detections
        )
        print("  ✅ Đã vẽ bounding boxes")
        # Bước 5: Lưu ảnh kết quả
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            output_dir = "results/visualize_detection"
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"{base_name}.jpg")
        cv2.imwrite(output_path, output_img)
        print(f"✅ Đã lưu kết quả: {output_path}")
        # In thống kê
        total_agree = sum(len(dets) for dets in agree_detections)
        total_disagree = sum(len(dets) for dets in disagree_detections)
        print(f"\n📊 THỐNG KÊ:")
        print(f"  - Tổng số detection ô đồng ý: {total_agree}")
        print(f"  - Tổng số detection ô không đồng ý: {total_disagree}")
        print(f"  - Tổng số ứng viên: 10")
        return output_img


def main():
    """Hàm main để chạy visualization"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Trực quan hóa kết quả detection trên phiếu bầu")
    parser.add_argument("--input", type=str, help="Đường dẫn ảnh phiếu bầu đầu vào")
    parser.add_argument("--output", type=str, default=None, help="Đường dẫn lưu ảnh kết quả (tùy chọn)")
    parser.add_argument("--weights", type=str, default="models/best.pt", help="Đường dẫn YOLO weights")
    parser.add_argument("--input_dir", type=str, help="Thư mục chứa ảnh để xử lý batch")
    parser.add_argument("--output_dir", type=str, help="Thư mục lưu kết quả batch")
    args = parser.parse_args()
    visualizer = BallotVisualizer(yolo_weights_path=args.weights)

    if args.input_dir:
        # Xử lý hàng loạt
        input_dir = args.input_dir
        output_dir = args.output_dir if args.output_dir else "results/visualize_detection_batch"
        os.makedirs(output_dir, exist_ok=True)
        # Lấy danh sách ảnh
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        image_files = [f for f in os.listdir(input_dir) if any(f.lower().endswith(ext) for ext in image_extensions)]
        print(f"🔍 Tìm thấy {len(image_files)} ảnh trong {input_dir}")
        success_count = 0
        for filename in image_files:
            image_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, f"detect_{os.path.splitext(filename)[0]}.jpg")
            result = visualizer.process_ballot(image_path, output_path)
            if result is not None:
                success_count += 1
        print(f"\n✅ Đã xử lý {success_count}/{len(image_files)} ảnh. Kết quả lưu tại: {output_dir}")
    elif args.input:
        # Xử lý một ảnh
        result = visualizer.process_ballot(
            args.input, 
            args.output
        )
        if result is not None:
            print("\n✅ HOÀN THÀNH!")
        else:
            print("\n❌ XỬ LÝ THẤT BẠI!")
    else:
        print("❌ Bạn phải truyền --input hoặc --input_dir")


if __name__ == "__main__":
    main()
