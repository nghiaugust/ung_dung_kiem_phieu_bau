"""
Model Services - Quản lý và cache models TrOCR và YOLO
Models được load một lần khi server khởi động và tái sử dụng cho mọi request
"""
import os
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from transformers import pipeline
from ultralytics import YOLO
from typing import List, Dict, Optional
import warnings
import io

warnings.filterwarnings("ignore", category=FutureWarning)


class TrOCRService:
    """Service để quản lý TrOCR model"""
    
    _instance = None
    _pipe = None
    
    def __new__(cls):
        """Singleton pattern để đảm bảo chỉ có 1 instance"""
        if cls._instance is None:
            cls._instance = super(TrOCRService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Khởi tạo service"""
        if self._pipe is None:
            self._load_model()
    
    def _load_model(self):
        """Load TrOCR model vào bộ nhớ"""
        try:
            # Kiểm tra GPU
            if torch.cuda.is_available():
                device = 0
                print("[TrOCR Service] ✅ Sử dụng GPU")
            else:
                device = -1
                print("[TrOCR Service] ⚠️ Sử dụng CPU")
            
            # Tìm đường dẫn model
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ai_core_dir = os.path.dirname(current_dir)
            model_trocr_root = os.path.join(ai_core_dir, "model_trocr")
            local_model_dir = os.path.join(
                model_trocr_root, 
                "models--microsoft--trocr-base-printed", 
                "snapshots"
            )
            local_model_dir = os.path.normpath(local_model_dir)
            
            # Tìm snapshot directory
            if not os.path.exists(local_model_dir):
                raise RuntimeError(f"Không tìm thấy thư mục model: {local_model_dir}")
            
            snapshot_dirs = [
                os.path.join(local_model_dir, d) 
                for d in os.listdir(local_model_dir) 
                if os.path.isdir(os.path.join(local_model_dir, d))
            ]
            
            if not snapshot_dirs:
                raise RuntimeError(f"Không tìm thấy snapshot trong {local_model_dir}")
            
            model_path = snapshot_dirs[0]
            
            # Load pipeline
            self._pipe = pipeline(
                "image-to-text",
                model=model_path,
                tokenizer=model_path,
                image_processor=model_path,
                framework="pt",
                device=device
            )
            
        except Exception as e:
            print(f"[TrOCR Service] ❌ Lỗi load model: {e}")
            raise
    
    def recognize_text(self, image_data: bytes, filename: str = "") -> Dict:
        """
        Nhận diện text từ ảnh
        
        Args:
            image_data: Dữ liệu ảnh dạng bytes
            filename: Tên file (để trả về kết quả)
            
        Returns:
            Dict chứa filename và text nhận diện được
        """
        pil_img = None
        try:
            # Convert bytes to PIL Image
            pil_img = Image.open(io.BytesIO(image_data))
            
            # Chuyển sang RGB nếu cần
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            
            # OCR
            result = self._pipe(pil_img)
            text = result[0]['generated_text'] if result else ""
            
            # XÓA result để giải phóng tensor memory
            del result
            
            return {
                'filename': filename,
                'text': text,
                'status': 'success'
            }
            
        except Exception as e:
            return {
                'filename': filename,
                'text': '',
                'status': 'error',
                'error': str(e)
            }
        finally:
            # CLEANUP: Đóng PIL image để giải phóng memory
            if pil_img is not None:
                pil_img.close()
            del pil_img
    
    def recognize_batch(self, images: List[tuple]) -> List[Dict]:
        """
        Nhận diện batch nhiều ảnh (tối ưu hơn xử lý từng ảnh)
        
        Args:
            images: List of (image_data, filename) tuples
            
        Returns:
            List of results
        """
        results = []
        pil_images = []
        
        try:
            # Prepare batch
            filenames = []
            
            for image_data, filename in images:
                try:
                    pil_img = Image.open(io.BytesIO(image_data))
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    pil_images.append(pil_img)
                    filenames.append(filename)
                except Exception as e:
                    results.append({
                        'filename': filename,
                        'text': '',
                        'status': 'error',
                        'error': f"Lỗi đọc ảnh: {str(e)}"
                    })
            
            # Batch prediction
            if pil_images:
                batch_results = self._pipe(pil_images)
                
                # batch_results có cấu trúc: [[{'generated_text': '...'}], [{'generated_text': '...'}]]
                # Mỗi element là một list chứa 1 dict
                for filename, result in zip(filenames, batch_results):
                    # result là list chứa dict, cần lấy phần tử đầu tiên
                    if isinstance(result, list) and len(result) > 0:
                        text = result[0].get('generated_text', '') if isinstance(result[0], dict) else ""
                    else:
                        text = ""
                    
                    results.append({
                        'filename': filename,
                        'text': text,
                        'status': 'success'
                    })
                
                # XÓA batch_results để giải phóng tensor memory
                del batch_results
            
        except Exception as e:
            # Fallback to individual processing
            print(f"[TrOCR Service] ⚠️ Batch processing failed, fallback to individual: {e}")
            for image_data, filename in images:
                results.append(self.recognize_text(image_data, filename))
        
        finally:
            # CLEANUP: Đóng tất cả PIL images
            for img in pil_images:
                try:
                    img.close()
                except:
                    pass
            del pil_images
        
        return results


def crop_center_horizontal(pil_img: Image.Image) -> Image.Image:
    """
    Cắt ảnh theo chiều dọc: bỏ 1/4 trái và 1/4 phải, giữ lại 1/2 giữa
    
    Args:
        pil_img: PIL Image gốc
        
    Returns:
        PIL Image đã được crop
    """
    width, height = pil_img.size
    
    # Tính toán vùng crop
    left = width // 4      # Cắt 1/4 bên trái
    right = 3 * width // 4 # Cắt 1/4 bên phải
    top = 0                # Giữ nguyên chiều cao
    bottom = height
    
    # Crop ảnh
    cropped_img = pil_img.crop((left, top, right, bottom))
    
    print(f"[Crop] Ảnh gốc: {width}x{height} -> Ảnh crop: {cropped_img.size[0]}x{cropped_img.size[1]}")
    
    return cropped_img


class YOLOService:
    """Service để quản lý YOLO model"""
    
    _instance = None
    _model = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super(YOLOService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Khởi tạo service"""
        if self._model is None:
            self._load_model()
    
    def _load_model(self):
        """Load YOLO model vào bộ nhớ"""
        try:
            # Tìm đường dẫn model
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ai_core_dir = os.path.dirname(current_dir)
            model_path = os.path.join(ai_core_dir, "model_yolo_x", "best.pt")
            model_path = os.path.normpath(model_path)
            
            if not os.path.exists(model_path):
                raise RuntimeError(f"Không tìm thấy YOLO weights: {model_path}")
            
            # Load model
            self._model = YOLO(model_path)
            
            # Check và set GPU
            if torch.cuda.is_available():
                self._model.to('cuda')  # Chuyển model lên GPU
                print("[YOLO Service] ✅ Sử dụng GPU")
            else:
                self._model.to('cpu')   # Đảm bảo model ở CPU
                print("[YOLO Service] ⚠️ Sử dụng CPU")
                
        except Exception as e:
            print(f"[YOLO Service] ❌ Lỗi load model: {e}")
            raise
    
    def detect(self, image_data: bytes, filename: str = "", image_path: str = None) -> Dict:
        """
        Detect dấu X trong ảnh
        
        Args:
            image_data: Dữ liệu ảnh dạng bytes
            filename: Tên file
            image_path: Đường dẫn ảnh gốc (để lưu ảnh có box)
            
        Returns:
            Dict chứa filename và kết quả detection
        """
        pil_img = None
        cropped_img = None
        img_array = None
        results = None
        
        try:
            # Convert bytes to PIL Image
            pil_img = Image.open(io.BytesIO(image_data))
            
            # Chuyển sang RGB nếu cần 
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            
            # CẮT ảnh: bỏ 1/4 trái và 1/4 phải, giữ 1/2 giữa
            cropped_img = crop_center_horizontal(pil_img)
            
            # Convert to numpy array (dùng ảnh đã crop)
            img_array = np.array(cropped_img)
            
            # Predict với các tham số 
            results = self._model.predict(
                source=img_array,
                save=False,
                verbose=False,
                conf=0.25,  # Confidence threshold
                iou=0.45    # IoU threshold for NMS
            )
            
            result = results[0]
            
            # Parse results
            detections = []
            label = "none"  # Mặc định không có gì
            
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes.xyxy.cpu().numpy()
                classes = result.boxes.cls.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_names = result.names
                
                for box, cls_id, conf in zip(boxes, classes, confidences):
                    cls_name = class_names[int(cls_id)]
                    detections.append({
                        'class': cls_name,
                        'confidence': float(conf),
                        'bbox': box.tolist()
                    })
                
                # XÓA numpy arrays ngay sau khi dùng xong
                del boxes, classes, confidences
                
                # Xác định label chính (ưu tiên x_mark)
                has_x_mark = any(d['class'] == 'x_mark' for d in detections)
                has_x_cancelled = any(d['class'] == 'x_cancelled' for d in detections)
                
                if has_x_mark:
                    label = "x_mark"
                elif has_x_cancelled:
                    label = "x_cancelled"
            
            # BỎ PHẦN VẼ BOX - chỉ trả về kết quả detection
            # if image_path:
            #     self._draw_detections(pil_img, detections, image_path, label)
            #     pil_img = None  # Đã được đóng trong _draw_detections
            
            return {
                'filename': filename,
                'label': label,
                'detections': detections,
                'status': 'success'
            }
            
        except Exception as e:
            return {
                'filename': filename,
                'label': 'none',
                'detections': [],
                'status': 'error',
                'error': str(e)
            }
        finally:
            # CLEANUP: Giải phóng memory
            if cropped_img is not None:
                cropped_img.close()
            if pil_img is not None:
                pil_img.close()
            del cropped_img
            del pil_img
            del img_array
            if results is not None:
                del results
    
    def _draw_detections(self, pil_img: Image.Image, detections: List[Dict], image_path: str, label: str = 'none'):
        """
        Vẽ bounding box lên ảnh và lưu lại
        
        Args:
            pil_img: PIL Image object (sẽ bị đóng sau khi save)
            detections: List các detection
            image_path: Đường dẫn để lưu ảnh
            label: Label chính (x_mark, x_cancelled, none)
        """
        draw = None
        font = None
        
        try:
            # Tạo draw object
            draw = ImageDraw.Draw(pil_img)
            
            # Thử load font (nếu không có thì dùng default)
            try:
                # Windows: Arial
                font = ImageFont.truetype("arial.ttf", 20)
            except:
                font = ImageFont.load_default()
            
            # Nếu không có detection, vẽ "none (0%)" ở góc trên trái
            if not detections or label == 'none':
                text = "none (0%)"
                # Vẽ background cho text
                text_bbox = draw.textbbox((10, 10), text, font=font)
                draw.rectangle(text_bbox, fill=(128, 128, 128))  # Màu xám
                # Vẽ text
                draw.text((10, 10), text, fill=(255, 255, 255), font=font)
            else:
                # Màu cho từng class
                color_map = {
                    'x_mark': (0, 255, 0),      # Xanh lá
                    'x_cancelled': (255, 0, 0),  # Đỏ
                }
                
                # Vẽ từng detection
                for det in detections:
                    bbox = det['bbox']  # [x1, y1, x2, y2]
                    cls_name = det['class']
                    conf = det['confidence']
                    
                    # Lấy màu theo class
                    color = color_map.get(cls_name, (255, 255, 0))  # Default: vàng
                    
                    # Vẽ rectangle
                    draw.rectangle(bbox, outline=color, width=3)
                    
                    # Tạo label text
                    label_text = f"{cls_name}: {conf:.0%}"
                    
                    # Vẽ background cho text
                    text_bbox = draw.textbbox((bbox[0], bbox[1] - 25), label_text, font=font)
                    draw.rectangle(text_bbox, fill=color)
                    
                    # Vẽ text
                    draw.text((bbox[0], bbox[1] - 25), label_text, fill=(255, 255, 255), font=font)
            
            # Lưu ảnh đè lên ảnh gốc
            pil_img.save(image_path)
            print(f"[YOLO Service] ✅ Đã lưu ảnh với detection: {os.path.basename(image_path)}")
            
        except Exception as e:
            print(f"[YOLO Service] ⚠️ Lỗi khi vẽ bounding box: {e}")
        finally:
            # CLEANUP: Đóng PIL image sau khi save
            del draw, font
            if pil_img is not None:
                pil_img.close()
            del pil_img
    
    def detect_batch(self, images: List[tuple]) -> List[Dict]:
        """
        Detect batch nhiều ảnh - TẬN DỤNG GPU PARALLEL PROCESSING
        
        Args:
            images: List of (image_data, filename, image_path) tuples
            
        Returns:
            List of results
        """
        results = []
        pil_images = []
        cropped_images = []
        img_arrays = []
        
        try:
            print(f"[YOLO Service] 🚀 Batch processing {len(images)} images")
            
            # Chuẩn bị batch (crop tất cả ảnh trước)
            filenames = []
            image_paths = []
            
            for item in images:
                # Hỗ trợ cả 2 format: (data, name) và (data, name, path)
                if len(item) == 3:
                    image_data, filename, image_path = item
                    image_paths.append(image_path)
                else:
                    image_data, filename = item[:2]
                    image_paths.append(None)
                
                try:
                    # Load và convert ảnh
                    pil_img = Image.open(io.BytesIO(image_data))
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    pil_images.append(pil_img)
                    
                    # Crop ảnh
                    cropped_img = crop_center_horizontal(pil_img)
                    cropped_images.append(cropped_img)
                    
                    # Convert to numpy
                    img_array = np.array(cropped_img)
                    img_arrays.append(img_array)
                    
                    filenames.append(filename)
                    
                except Exception as e:
                    results.append({
                        'filename': filename,
                        'label': 'none',
                        'detections': [],
                        'status': 'error',
                        'error': f"Lỗi đọc ảnh: {str(e)}"
                    })
            
            # BATCH PREDICTION - GPU xử lý SONG SONG tất cả ảnh
            if img_arrays:
                batch_results = self._model.predict(
                    source=img_arrays,
                    save=False,
                    verbose=False,
                    conf=0.25,
                    iou=0.45,
                    stream=False  # Đảm bảo trả về list results
                )
                
                # Parse từng result
                for filename, result, image_path in zip(filenames, batch_results, image_paths):
                    detections = []
                    label = "none"
                    
                    if result.boxes is not None and len(result.boxes) > 0:
                        boxes = result.boxes.xyxy.cpu().numpy()
                        classes = result.boxes.cls.cpu().numpy()
                        confidences = result.boxes.conf.cpu().numpy()
                        class_names = result.names
                        
                        for box, cls_id, conf in zip(boxes, classes, confidences):
                            cls_name = class_names[int(cls_id)]
                            detections.append({
                                'class': cls_name,
                                'confidence': float(conf),
                                'bbox': box.tolist()
                            })
                        
                        # XÓA numpy arrays
                        del boxes, classes, confidences
                        
                        # Xác định label chính
                        has_x_mark = any(d['class'] == 'x_mark' for d in detections)
                        has_x_cancelled = any(d['class'] == 'x_cancelled' for d in detections)
                        
                        if has_x_mark:
                            label = "x_mark"
                        elif has_x_cancelled:
                            label = "x_cancelled"
                    
                    results.append({
                        'filename': filename,
                        'label': label,
                        'detections': detections,
                        'status': 'success'
                    })
                
                # Cleanup batch results
                del batch_results
                
                print(f"[YOLO Service] ✅ Batch processed {len(results)} images successfully")
                
        except Exception as e:
            # Fallback to individual processing
            print(f"[YOLO Service] ⚠️ Batch failed, fallback to individual: {e}")
            results = []
            for item in images:
                if len(item) == 3:
                    image_data, filename, image_path = item
                    result = self.detect(image_data, filename, image_path)
                else:
                    image_data, filename = item
                    result = self.detect(image_data, filename)
                results.append(result)
        
        finally:
            # CLEANUP: Giải phóng tất cả images
            for img in cropped_images:
                try:
                    img.close()
                except:
                    pass
            for img in pil_images:
                try:
                    img.close()
                except:
                    pass
            del pil_images, cropped_images, img_arrays
        
        return results
