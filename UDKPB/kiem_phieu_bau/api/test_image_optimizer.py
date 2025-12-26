"""
Script test module image_optimizer với folder input/output
Chạy: python test_image_optimizer.py <input_folder> <output_folder>
"""

import cv2
import numpy as np
import os
import sys
import glob
from pathlib import Path


def optimize_image_standalone(input_path, output_path, target_width=2480, quality=85, apply_clahe=True):
    """
    Tối ưu ảnh phiếu bầu (standalone version - không cần Django)
    
    Args:
        input_path: Đường dẫn file ảnh đầu vào
        output_path: Đường dẫn file ảnh đầu ra
        target_width: Chiều rộng mục tiêu (px). Default 2480px
        quality: Chất lượng JPEG (1-100). Default 85
        apply_clahe: Có áp dụng CLAHE không. Default True
        
    Returns:
        dict: Thông tin tối ưu
    """
    try:
        # Đọc ảnh
        img = cv2.imread(input_path)
        
        if img is None:
            raise ValueError(f"Không thể đọc ảnh: {input_path}")
        
        height, width = img.shape[:2]
        original_size = os.path.getsize(input_path)
        
        # 1. Chuyển sang grayscale
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        # 2. Resize nếu cần
        if width > target_width:
            aspect_ratio = height / width
            new_width = target_width
            new_height = int(target_width * aspect_ratio)
            gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # 3. CLAHE - Tăng độ tương phản
        if apply_clahe:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
        
        # 4. Denoise - Khử nhiễu
        gray = cv2.fastNlMeansDenoising(gray, None, h=5, templateWindowSize=7, searchWindowSize=21)
        
        # 5. Lưu với JPEG compression
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        
        # Đổi extension thành .jpg
        output_path_jpg = str(Path(output_path).with_suffix('.jpg'))
        
        success = cv2.imwrite(output_path_jpg, gray, encode_param)
        
        if not success:
            raise ValueError(f"Không thể lưu ảnh: {output_path_jpg}")
        
        # Lấy kích thước file output
        optimized_size = os.path.getsize(output_path_jpg)
        size_reduction_percent = ((original_size - optimized_size) / original_size) * 100
        
        return {
            'success': True,
            'input_path': input_path,
            'output_path': output_path_jpg,
            'original_width': width,
            'original_height': height,
            'optimized_width': gray.shape[1],
            'optimized_height': gray.shape[0],
            'original_size_kb': original_size / 1024,
            'optimized_size_kb': optimized_size / 1024,
            'saved_kb': (original_size - optimized_size) / 1024,
            'reduction_percent': size_reduction_percent
        }
        
    except Exception as e:
        return {
            'success': False,
            'input_path': input_path,
            'error': str(e)
        }


def process_folder(input_folder, output_folder, target_width=2480, quality=85):
    """
    Xử lý tất cả ảnh trong folder
    
    Args:
        input_folder: Folder chứa ảnh gốc
        output_folder: Folder lưu ảnh đã tối ưu
        target_width: Chiều rộng mục tiêu
        quality: Chất lượng JPEG
    """
    # Tạo output folder nếu chưa có
    os.makedirs(output_folder, exist_ok=True)
    
    # Tìm tất cả file ảnh
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.JPG', '*.JPEG', '*.PNG', '*.BMP', '*.TIFF']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(input_folder, ext)))
    
    # Loại bỏ trùng lặp
    image_files = list(set(os.path.normpath(f) for f in image_files))
    image_files.sort()
    
    if not image_files:
        print(f"❌ Không tìm thấy ảnh nào trong {input_folder}")
        return
    
    print("=" * 80)
    print("IMAGE OPTIMIZER - TEST SCRIPT")
    print("=" * 80)
    print(f"📁 Input:  {os.path.abspath(input_folder)}")
    print(f"📁 Output: {os.path.abspath(output_folder)}")
    print(f"🔍 Tìm thấy: {len(image_files)} ảnh")
    print(f"⚙️  Settings: target_width={target_width}px, quality={quality}")
    print("=" * 80)
    print()
    
    results = []
    total_original_size = 0
    total_optimized_size = 0
    success_count = 0
    fail_count = 0
    
    for idx, input_path in enumerate(image_files, 1):
        filename = os.path.basename(input_path)
        output_path = os.path.join(output_folder, filename)
        
        print(f"[{idx}/{len(image_files)}] Processing: {filename}")
        
        result = optimize_image_standalone(input_path, output_path, target_width, quality)
        results.append(result)
        
        if result['success']:
            success_count += 1
            total_original_size += result['original_size_kb']
            total_optimized_size += result['optimized_size_kb']
            
            print(f"  ✅ Original:  {result['original_width']}x{result['original_height']}, {result['original_size_kb']:.1f} KB")
            print(f"     Optimized: {result['optimized_width']}x{result['optimized_height']}, {result['optimized_size_kb']:.1f} KB")
            print(f"     Reduction: {result['reduction_percent']:.1f}% (saved {result['saved_kb']:.1f} KB)")
        else:
            fail_count += 1
            print(f"  ❌ Error: {result['error']}")
        
        print()
    
    # Tổng kết
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"✅ Success: {success_count}/{len(image_files)}")
    print(f"❌ Failed:  {fail_count}/{len(image_files)}")
    
    if success_count > 0:
        avg_reduction = ((total_original_size - total_optimized_size) / total_original_size) * 100
        print(f"\n💾 Storage:")
        print(f"  - Total original:  {total_original_size / 1024:.1f} MB")
        print(f"  - Total optimized: {total_optimized_size / 1024:.1f} MB")
        print(f"  - Total saved:     {(total_original_size - total_optimized_size) / 1024:.1f} MB")
        print(f"  - Average reduction: {avg_reduction:.1f}%")
    
    print("=" * 80)


def main():
    """Main function"""
    if len(sys.argv) < 3:
        print("=" * 80)
        print("IMAGE OPTIMIZER - TEST SCRIPT")
        print("=" * 80)
        print("\nCách dùng:")
        print(f"  python {os.path.basename(__file__)} <input_folder> <output_folder> [target_width] [quality]")
        print("\nTham số:")
        print("  input_folder   : Folder chứa ảnh gốc")
        print("  output_folder  : Folder lưu ảnh đã tối ưu")
        print("  target_width   : Chiều rộng mục tiêu (px) - optional, default 2480")
        print("  quality        : Chất lượng JPEG (1-100) - optional, default 85")
        print("\nVí dụ:")
        print(f"  python {os.path.basename(__file__)} ./input ./output")
        print(f"  python {os.path.basename(__file__)} ./input ./output 1920 80")
        print(f"  python {os.path.basename(__file__)} C:\\images\\raw C:\\images\\optimized")
        print("=" * 80)
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_folder = sys.argv[2]
    target_width = int(sys.argv[3]) if len(sys.argv) > 3 else 2480
    quality = int(sys.argv[4]) if len(sys.argv) > 4 else 85
    
    # Validate input folder
    if not os.path.exists(input_folder):
        print(f"❌ Lỗi: Folder input không tồn tại: {input_folder}")
        sys.exit(1)
    
    if not os.path.isdir(input_folder):
        print(f"❌ Lỗi: Input không phải là folder: {input_folder}")
        sys.exit(1)
    
    # Validate parameters
    if target_width < 100 or target_width > 10000:
        print(f"❌ Lỗi: target_width phải trong khoảng 100-10000 (nhận: {target_width})")
        sys.exit(1)
    
    if quality < 1 or quality > 100:
        print(f"❌ Lỗi: quality phải trong khoảng 1-100 (nhận: {quality})")
        sys.exit(1)
    
    # Process
    process_folder(input_folder, output_folder, target_width, quality)


if __name__ == "__main__":
    main()
