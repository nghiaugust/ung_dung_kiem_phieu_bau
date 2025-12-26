"""
Module tối ưu ảnh phiếu bầu để giảm dung lượng lưu trữ
- Chuyển ảnh sang grayscale (giảm 66% dung lượng)
- Tăng độ tương phản (CLAHE) để OCR tốt hơn
- Resize về kích thước chuẩn hóa
- Nén JPEG với quality phù hợp
- Đảm bảo chất lượng cho YOLO và TrOCR
"""

import cv2
import numpy as np
from PIL import Image
import io
from django.core.files.uploadedfile import InMemoryUploadedFile
import tempfile
import os


def optimize_ballot_image(uploaded_file, target_width=2480, quality=85, apply_clahe=True):
    """
    Tối ưu ảnh phiếu bầu để giảm dung lượng nhưng vẫn đảm bảo chất lượng cho model
    
    Args:
        uploaded_file: Django UploadedFile object
        target_width: Chiều rộng mục tiêu (px). Chiều cao tự động theo tỷ lệ. Default 2480px (~21cm ở 300 DPI)
        quality: Chất lượng JPEG (1-100). Default 85
        apply_clahe: Có áp dụng CLAHE để tăng độ tương phản không. Default True
        
    Returns:
        InMemoryUploadedFile: File ảnh đã tối ưu
        
    Note:
        - Giữ nguyên tên file gốc nhưng đổi extension thành .jpg
        - Ảnh output là grayscale (1 channel)
        - DPI 300: 2480px = ~21cm (A4 width)
    """
    temp_file_path = None
    
    try:
        # Lưu file tạm để đọc bằng OpenCV
        file_ext = uploaded_file.name.split('.')[-1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name
        
        # Đọc ảnh bằng OpenCV
        img = cv2.imread(temp_file_path)
        
        if img is None:
            raise ValueError(f"Không thể đọc ảnh từ file: {uploaded_file.name}")
        
        height, width = img.shape[:2]
        original_size = uploaded_file.size
        
        # 1. Chuyển sang grayscale (giảm 66% dung lượng)
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        # 2. Resize về kích thước chuẩn (nếu ảnh lớn hơn target)
        if width > target_width:
            # Tính chiều cao mới theo tỷ lệ
            aspect_ratio = height / width
            new_width = target_width
            new_height = int(target_width * aspect_ratio)
            
            # Resize với interpolation INTER_AREA (tốt nhất cho downscale)
            gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # 3. Tăng độ tương phản bằng CLAHE (Contrast Limited Adaptive Histogram Equalization)
        if apply_clahe:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        
        # 4. Làm mịn nhẹ để giảm nhiễu (giúp nén tốt hơn)
        gray = cv2.fastNlMeansDenoising(gray, None, h=5, templateWindowSize=7, searchWindowSize=21)
        
        # 5. Nén JPEG với quality phù hợp
        # Encode sang JPEG trong memory
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, buffer = cv2.imencode('.jpg', gray, encode_param)
        
        if not success:
            raise ValueError("Không thể encode ảnh sang JPEG")
        
        # Chuyển buffer thành BytesIO
        img_io = io.BytesIO(buffer.tobytes())
        img_io.seek(0)
        
        # Tạo tên file mới (đổi extension thành .jpg)
        original_name = uploaded_file.name
        name_without_ext = '.'.join(original_name.split('.')[:-1])
        new_filename = f"{name_without_ext}.jpg"
        
        # Tạo InMemoryUploadedFile mới
        optimized_file = InMemoryUploadedFile(
            file=img_io,
            field_name=uploaded_file.field_name,
            name=new_filename,
            content_type='image/jpeg',
            size=len(buffer),
            charset=None
        )
        
        # Log thông tin tối ưu
        optimized_size = len(buffer)
        size_reduction_percent = ((original_size - optimized_size) / original_size) * 100
        
        print(f"[IMAGE OPTIMIZER] {original_name}:")
        print(f"  - Original: {width}x{height}, {original_size / 1024:.1f} KB")
        print(f"  - Optimized: {gray.shape[1]}x{gray.shape[0]}, {optimized_size / 1024:.1f} KB")
        print(f"  - Reduction: {size_reduction_percent:.1f}% (saved {(original_size - optimized_size) / 1024:.1f} KB)")
        
        return optimized_file
        
    finally:
        # Xóa file tạm
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass


def optimize_ballot_image_aggressive(uploaded_file, target_width=1920, quality=80):
    """
    Tối ưu ảnh phiếu bầu ở mức aggressive hơn (giảm dung lượng nhiều hơn)
    
    Args:
        uploaded_file: Django UploadedFile object
        target_width: Chiều rộng mục tiêu (px). Default 1920px (~16cm ở 300 DPI)
        quality: Chất lượng JPEG (1-100). Default 80
        
    Returns:
        InMemoryUploadedFile: File ảnh đã tối ưu
    """
    return optimize_ballot_image(uploaded_file, target_width=target_width, quality=quality, apply_clahe=True)


def get_image_info(uploaded_file):
    """
    Lấy thông tin cơ bản của ảnh (để debug)
    
    Args:
        uploaded_file: Django UploadedFile object
        
    Returns:
        dict: Thông tin ảnh
    """
    temp_file_path = None
    
    try:
        file_ext = uploaded_file.name.split('.')[-1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as temp_file:
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name
        
        # Đọc ảnh bằng OpenCV
        img = cv2.imread(temp_file_path)
        
        if img is None:
            return None
        
        height, width = img.shape[:2]
        channels = img.shape[2] if len(img.shape) == 3 else 1
        
        return {
            'width': width,
            'height': height,
            'channels': channels,
            'size_bytes': uploaded_file.size,
            'size_kb': uploaded_file.size / 1024,
            'size_mb': uploaded_file.size / (1024 * 1024)
        }
        
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass
