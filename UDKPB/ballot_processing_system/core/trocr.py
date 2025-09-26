# nhan_dien_trocr.py
import torch
from transformers import pipeline
from PIL import Image, ImageEnhance, ImageFilter
import warnings
import cv2
import numpy as np
import re

# Tắt warning về deprecated class
warnings.filterwarnings("ignore", category=FutureWarning)

# Khởi tạo pipeline global để tái sử dụng
_pipe = None

def get_pipeline():
    """
    Lazy loading pipeline để tối ưu performance
    """
    global _pipe
    if _pipe is None:
        # Kiểm tra GPU
        if torch.cuda.is_available():
            device = 0
            print("[INFO] Đang sử dụng GPU cho TrOCR!")
        else:
            device = -1
            print("[INFO] Không có GPU, TrOCR sẽ chạy trên CPU.")
        # Đường dẫn local tới model đã tải về
        import os
        import os
        # Tìm thư mục gốc project (nơi có ballot_processing_system)
        cur = os.path.abspath(__file__)
        while True:
            parent = os.path.dirname(cur)
            if os.path.isdir(os.path.join(parent, "model_trocr")):
                model_trocr_root = os.path.join(parent, "model_trocr")
                break
            if parent == cur:
                raise RuntimeError("Không tìm thấy thư mục model_trocr trong cây thư mục cha!")
            cur = parent
        local_model_dir = os.path.join(model_trocr_root, "models--microsoft--trocr-base-printed", "snapshots")
        local_model_dir = os.path.normpath(local_model_dir)
        # Tìm thư mục snapshot id (thường chỉ có 1 thư mục con)
        snapshot_dirs = [os.path.join(local_model_dir, d) for d in os.listdir(local_model_dir) if os.path.isdir(os.path.join(local_model_dir, d))]
        if not snapshot_dirs:
            raise RuntimeError(f"Không tìm thấy model TrOCR đã tải về trong {local_model_dir}. Hãy chắc chắn đã tải model!")
        model_path = snapshot_dirs[0]
        _pipe = pipeline(
            "image-to-text",
            model=model_path,
            tokenizer=model_path,
            image_processor=model_path,
            framework="pt",
            device=device
        )
        print(f"[INFO] TrOCR pipeline đã được khởi tạo từ local: {model_path}")
    return _pipe

def tien_xu_ly_anh_ocr(pil_img):
    """
    Tiền xử lý ảnh để cải thiện OCR
    """
    # Chuyển sang numpy array để xử lý với OpenCV
    img_array = np.array(pil_img)
    
    # Chuyển sang grayscale
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    # 1. Khử nhiễu
    denoised = cv2.medianBlur(gray, 3)
    
    # 2. Cải thiện độ tương phản
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    
    # 3. Threshold để tạo ảnh nhị phân rõ nét
    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 4. Morphological operations để làm sạch
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    # Chuyển về PIL Image
    return Image.fromarray(cleaned)

def cat_tu_rieng_biet(pil_img):
    """
    Cắt từng từ riêng biệt để OCR
    """
    # Chuyển sang numpy array
    img_array = np.array(pil_img)
    
    # Chuyển sang grayscale nếu cần
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    # Threshold
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Tìm contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Lọc và sắp xếp contours
    word_boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        # Lọc những vùng quá nhỏ
        if w > 10 and h > 10:
            word_boxes.append((x, y, w, h))
    
    # Sắp xếp từ trái sang phải
    word_boxes.sort(key=lambda box: box[0])
    
    # Cắt từng từ
    words = []
    for x, y, w, h in word_boxes:
        # Thêm padding
        padding = 5
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(pil_img.width, x + w + padding)
        y2 = min(pil_img.height, y + h + padding)
        
        word_img = pil_img.crop((x1, y1, x2, y2))
        words.append(word_img)
    
    return words

def hau_xu_ly_text(text):
    """
    Hậu xử lý text để sửa lỗi thường gặp
    """
    if not text:
        return ""
    
    # Dictionary để sửa các lỗi OCR thường gặp
    replacements = {
        '0': 'O',  # Số 0 thành chữ O
        '1': 'I',  # Số 1 thành chữ I
        '5': 'S',  # Số 5 thành chữ S
        '8': 'B',  # Số 8 thành chữ B
        '@': 'A',  # @ thành A
        '|': 'I',  # | thành I
        '!': 'I',  # ! thành I
        '€': 'E',  # € thành E
        'ﬁ': 'fi', # ligature fi
        'ﬂ': 'fl', # ligature fl
    }
    
    # Áp dụng replacements
    processed_text = text
    for old, new in replacements.items():
        processed_text = processed_text.replace(old, new)
    
    # Loại bỏ ký tự đặc biệt không mong muốn
    processed_text = re.sub(r'[^\w\s\-\.]', '', processed_text)
    
    # Chuẩn hóa khoảng trắng
    processed_text = ' '.join(processed_text.split())
    
    return processed_text.strip()

def doc_ten_tu_anh(duong_dan_anh):
    """
    Đọc tên từ ảnh bằng phương pháp cắt từng từ
    """
    try:
        # Lấy pipeline
        pipe = get_pipeline()
        
        pil_img = Image.open(duong_dan_anh)
        
        # Chuyển sang RGB nếu cần
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')
        
        # Cắt từng từ riêng biệt
        words = cat_tu_rieng_biet(pil_img)
        word_texts = []
        
        for word_img in words:
            # Tiền xử lý từng từ
            enhanced_word = tien_xu_ly_anh_ocr(word_img)
            result = pipe(enhanced_word)
            if result:
                word_text = result[0]['generated_text']
                word_texts.append(word_text)
        
        # Ghép các từ lại
        text = ' '.join(word_texts)
        
        # Hậu xử lý
        processed_text = hau_xu_ly_text(text)
        
        return processed_text
        
    except Exception as e:
        print(f"Lỗi khi xử lý ảnh {duong_dan_anh}: {str(e)}")
        return None

if __name__ == "__main__":
    import os
    
    thu_muc = "ket_qua_tien_xu_ly_v2/"
    
    # Tìm tất cả file có chứa "hoten" trong tên
    files_hoten = []
    if os.path.exists(thu_muc):
        for filename in os.listdir(thu_muc):
            if "hoten" in filename.lower() and filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                files_hoten.append(os.path.join(thu_muc, filename))
    
    if not files_hoten:
        print(f"Không tìm thấy file nào có chứa 'hoten' trong thư mục: {thu_muc}")
    else:
        print("=== OCR BẰNG PHƯƠNG PHÁP CẮT TỪNG TỪ ===")
        print(f"Tìm thấy {len(files_hoten)} file(s) chứa 'hoten'")
        print("-" * 50)
        
        for i, duong_dan_anh in enumerate(files_hoten, 1):
            print(f"\n[{i}/{len(files_hoten)}] Đang xử lý: {os.path.basename(duong_dan_anh)}")
            try:
                result = doc_ten_tu_anh(duong_dan_anh)
                print(f"Kết quả OCR: '{result}'")
            except Exception as e:
                print(f"Lỗi: {str(e)}")
        
        print(f"\n=== HOÀN THÀNH XỬ LÝ {len(files_hoten)} FILE ===")
