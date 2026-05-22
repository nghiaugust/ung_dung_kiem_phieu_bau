import cv2
import numpy as np
import tempfile
import os
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from io import BytesIO
from PIL import Image


def optimize_ballot_image(uploaded_file, max_size_kb=500, quality=85):
    """
    Tối ưu ảnh phiếu bầu để giảm dung lượng nhưng vẫn đảm bảo VietNameOCR và YOLO nhận diện tốt
    
    Args:
        uploaded_file: Django UploadedFile object
        max_size_kb: Dung lượng tối đa mong muốn (KB)
        quality: JPEG quality (0-100), mặc định 85
    
    Returns:
        BytesIO object chứa ảnh đã tối ưu
    """
    try:
        # 1. Đọc ảnh từ uploaded file
        if isinstance(uploaded_file, InMemoryUploadedFile):
            # File nhỏ, đã ở trong memory
            file_bytes = uploaded_file.read()
            uploaded_file.seek(0)  # Reset con trỏ file
        else:
            # File lớn, đọc từ disk
            uploaded_file.seek(0)
            file_bytes = uploaded_file.read()
            uploaded_file.seek(0)  # Reset con trỏ file
        
        # DEBUG: Dung lượng file gốc
        original_size_kb = len(file_bytes) / 1024
        
        # Convert bytes to numpy array
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise ValueError("Không thể đọc ảnh")
        
        # 2. Lọc nhiễu nhẹ để giảm dung lượng khi nén
        # Sử dụng bilateral filter để giữ cạnh sắc nét (quan trọng cho YOLO)
        denoised = cv2.bilateralFilter(img, d=5, sigmaColor=50, sigmaSpace=50)
        
        # 3. Tăng độ tương phản nhẹ để chữ rõ hơn (tốt cho VietNameOCR)
        # Convert to LAB color space
        lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to L channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        # Merge channels
        enhanced = cv2.merge([l, a, b])
        final_img = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        
        # 4. Encode thành JPEG với quality được chỉ định
        # JPEG tốt hơn WebP về độ tương thích và vẫn nén tốt
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, buffer = cv2.imencode('.jpg', final_img, encode_param)
        
        # 5. Kiểm tra kích thước, nếu vẫn quá lớn thì giảm quality
        current_size_kb = len(buffer) / 1024
        
        if current_size_kb > max_size_kb and quality > 60:
            # Thử giảm quality
            new_quality = max(60, int(quality * (max_size_kb / current_size_kb)))
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), new_quality]
            _, buffer = cv2.imencode('.jpg', final_img, encode_param)
        
        # 6. Convert sang BytesIO để trả về
        result = BytesIO(buffer.tobytes())
        result.seek(0)
        
        # DEBUG: Tổng kết
        final_size_kb = len(buffer) / 1024
        compression_ratio = (1 - final_size_kb / original_size_kb) * 100
        print(f"[IMAGE_OPTIMIZER] ✓ Hoàn thành: {original_size_kb:.2f} KB → {final_size_kb:.2f} KB (giảm {compression_ratio:.1f}%)")
        
        return result
        
    except Exception as e:
        # Nếu có lỗi, trả về file gốc
        print(f"[WARNING] Lỗi khi tối ưu ảnh: {e}, sử dụng file gốc")
        uploaded_file.seek(0)
        original = BytesIO(uploaded_file.read())
        original.seek(0)
        uploaded_file.seek(0)
        return original
