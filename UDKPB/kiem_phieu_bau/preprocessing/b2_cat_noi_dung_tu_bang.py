"""
Phát hiện cấu trúc bảng bằng Line Detection (OpenCV)
Độ chính xác cao hơn cho bảng có đường kẻ rõ ràng
Kết hợp Preprocessing + Edge Projection
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw
import os
from scipy.signal import find_peaks
import matplotlib.pyplot as plt


def tien_xu_ly_anh(gray):
    """
    PHƯƠNG ÁN 8: Tiền xử lý ảnh
    - Khử nhiễu
    - Làm nét đường kẻ
    
    Args:
        gray: Ảnh grayscale
        
    Returns:
        processed: Ảnh đã xử lý
    """
    print("[INFO] Bước 1: Tiền xử lý ảnh (Denoise + Sharpen)...")
    
    # 1. Khử nhiễu
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    
    # 2. Làm nét đường kẻ bằng kernel sharpen
    sharpen_kernel = np.array([
        [-1, -1, -1],
        [-1,  9, -1],
        [-1, -1, -1]
    ])
    sharpened = cv2.filter2D(denoised, -1, sharpen_kernel)
    
    # 3. Tăng độ tương phản
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(sharpened)
    
    return enhanced


def chieu_edge_theo_truc(edges, truc='y'):
    """
    PHƯƠNG ÁN 5: Chiếu edges lên trục để tìm đường kẻ
    
    Args:
        edges: Ảnh edges (từ Canny)
        truc: 'y' cho đường ngang, 'x' cho đường dọc
        
    Returns:
        projection: Mảng histogram chiếu
    """
    if truc == 'y':
        # Chiếu theo trục Y (tính tổng pixel trắng theo từng hàng) → Tìm đường NGANG
        projection = np.sum(edges, axis=1)
    else:
        # Chiếu theo trục X (tính tổng pixel trắng theo từng cột) → Tìm đường DỌC
        projection = np.sum(edges, axis=0)
    
    return projection


def tim_duong_tu_projection(projection, min_distance=20, height_threshold=None):
    """
    Tìm vị trí đường kẻ từ projection histogram bằng cách tìm peaks
    
    Args:
        projection: Mảng histogram chiếu
        min_distance: Khoảng cách tối thiểu giữa 2 peaks (pixels)
        height_threshold: Ngưỡng chiều cao của peak (None = tự động)
        
    Returns:
        peaks: Danh sách vị trí các đường kẻ
    """
    # Tự động tính threshold nếu không cung cấp
    if height_threshold is None:
        height_threshold = np.mean(projection) + 0.5 * np.std(projection)
    
    # Tìm peaks trong histogram
    peaks, properties = find_peaks(
        projection, 
        height=height_threshold,
        distance=min_distance,
        prominence=height_threshold * 0.3
    )
    
    return peaks


def tim_threshold_tu_dong(projection, target_count, min_distance, max_iterations=100):
    """
    Tự động tìm threshold tối ưu để có được số lượng đường mong muốn
    Sử dụng thuật toán tìm kiếm nhị phân
    
    Args:
        projection: Mảng histogram chiếu
        target_count: Số lượng đường mong muốn
        min_distance: Khoảng cách tối thiểu giữa các peaks
        max_iterations: Số lần lặp tối đa
        
    Returns:
        tuple: (best_threshold, best_peaks)
    """
    max_projection = np.max(projection)
    min_projection = np.min(projection[projection > 0]) if np.any(projection > 0) else 0
    
    # Khởi tạo khoảng tìm kiếm
    low_threshold = min_projection
    high_threshold = max_projection
    
    best_threshold = None
    best_peaks = None
    best_diff = float('inf')
    
    print(f"[INFO] Tìm kiếm nhị phân threshold (mục tiêu: {target_count} đường)...")
    print(f"[INFO] Khoảng tìm kiếm: [{low_threshold:.0f}, {high_threshold:.0f}]")
    
    for iteration in range(max_iterations):
        # Lấy threshold ở giữa
        current_threshold = (low_threshold + high_threshold) / 2
        
        # Tìm peaks với threshold hiện tại
        current_peaks = tim_duong_tu_projection(projection, min_distance, current_threshold)
        current_count = len(current_peaks)
        
        # Tính độ lệch
        diff = abs(current_count - target_count)
        
        # Cập nhật best nếu tốt hơn
        if diff < best_diff:
            best_diff = diff
            best_threshold = current_threshold
            best_peaks = current_peaks
        
        # In thông tin debug
        if iteration % 10 == 0 or diff == 0:
            print(f"  Lần {iteration+1}: threshold={current_threshold:.0f}, tìm được {current_count} đường (lệch {diff})")
        
        # Nếu đã khớp hoàn toàn, dừng
        if diff == 0:
            print(f"[SUCCESS] Tìm thấy threshold tối ưu sau {iteration+1} lần lặp!")
            break
        
        # Điều chỉnh khoảng tìm kiếm
        if current_count < target_count:
            # Quá ít đường → giảm threshold
            high_threshold = current_threshold
        else:
            # Quá nhiều đường → tăng threshold
            low_threshold = current_threshold
        
        # Nếu khoảng tìm kiếm quá nhỏ, dừng
        if high_threshold - low_threshold < 1:
            print(f"[INFO] Khoảng tìm kiếm quá nhỏ, dừng tại lần {iteration+1}")
            break
    
    if best_diff > 0:
        print(f"[WARNING] Không tìm được threshold hoàn hảo. Kết quả tốt nhất: {len(best_peaks)} đường (lệch {best_diff})")
    
    return best_threshold, best_peaks


def ve_bieu_do_projection(h_projection, v_projection, h_peaks, v_peaks, duong_dan_anh, h_threshold=None, v_threshold=None):
    """
    Vẽ biểu đồ histogram cho projection của đường ngang và đường dọc
    
    Args:
        h_projection: Projection histogram cho đường ngang
        v_projection: Projection histogram cho đường dọc
        h_peaks: Vị trí các đường ngang đã phát hiện
        v_peaks: Vị trí các đường dọc đã phát hiện
        duong_dan_anh: Đường dẫn ảnh gốc (để lưu biểu đồ)
        h_threshold: Threshold cho đường ngang (None = tính tự động)
        v_threshold: Threshold cho đường dọc (None = tính tự động)
    """
    # Tính threshold mặc định nếu không có
    if h_threshold is None:
        h_threshold = np.max(h_projection) * 0.3
    if v_threshold is None:
        v_threshold = np.max(v_projection) * 0.4
    
    plt.figure(figsize=(12, 5))
    
    # Biểu đồ cho đường NGANG
    plt.subplot(1, 2, 1)
    plt.plot(h_projection, range(len(h_projection)), 'b-', linewidth=1)
    plt.axvline(x=h_threshold, color='r', linestyle='--', label=f'Threshold={h_threshold:.0f}')
    for idx, y in enumerate(h_peaks):
        plt.plot(h_projection[y], y, 'ro', markersize=8)
        plt.text(h_projection[y] + 50, y, f'H{idx}', fontsize=9, color='red')
    plt.xlabel('Intensity (Tổng edges theo hàng)', fontsize=10)
    plt.ylabel('Y (pixels)', fontsize=10)
    plt.title('Projection theo trục Y - Phát hiện ĐƯỜNG NGANG', fontsize=12, fontweight='bold')
    plt.gca().invert_yaxis()  # Đảo trục Y để khớp với tọa độ ảnh
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # Biểu đồ cho đường DỌC
    plt.subplot(1, 2, 2)
    plt.plot(range(len(v_projection)), v_projection, 'g-', linewidth=1)
    plt.axhline(y=v_threshold, color='r', linestyle='--', label=f'Threshold={v_threshold:.0f}')
    for idx, x in enumerate(v_peaks):
        plt.plot(x, v_projection[x], 'ro', markersize=8)
        plt.text(x, v_projection[x] + 50, f'V{idx}', fontsize=9, color='red')
    plt.xlabel('X (pixels)', fontsize=10)
    plt.ylabel('Intensity (Tổng edges theo cột)', fontsize=10)
    plt.title('Projection theo trục X - Phát hiện ĐƯỜNG DỌC', fontsize=12, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    plt.tight_layout()
    
    # Lưu đồ thị
    base_name = os.path.splitext(duong_dan_anh)[0]
    plt.savefig(f"{base_name}_projection_histogram.png", dpi=150, bbox_inches='tight')
    print(f"[INFO] Đã lưu đồ thị projection: {base_name}_projection_histogram.png")
    plt.close()


def phat_hien_duong_ke_edge_projection(duong_dan_anh, hien_thi=True, target_h_lines=None, target_v_lines=None):
    """
    PHƯƠNG ÁN 8 + 5: Phát hiện đường kẻ bằng Edge Projection
    
    Args:
        duong_dan_anh: Đường dẫn tới ảnh
        hien_thi: Có vẽ kết quả lên ảnh không
        target_h_lines: Số đường ngang mong muốn (None = tự động)
        target_v_lines: Số đường dọc mong muốn (None = tự động)
        
    Returns:
        dict: {'horizontal_lines': [...], 'vertical_lines': [...], 'grid': [[...]]}
    """
    # 1. Đọc ảnh
    img = cv2.imread(duong_dan_anh)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    
    print(f"[INFO] Kích thước ảnh: {width}x{height}")
    
    # 2. PHƯƠNG ÁN 8: Tiền xử lý
    enhanced = tien_xu_ly_anh(gray)
    
    # 3. Edge Detection
    print("[INFO] Bước 2: Phát hiện edges (Canny)...")
    edges = cv2.Canny(enhanced, 50, 150, apertureSize=3)
    
    # 4. PHƯƠNG ÁN 5: Edge Projection cho đường NGANG
    print("[INFO] Bước 3: Chiếu edges theo trục Y (tìm đường NGANG)...")
    h_projection = chieu_edge_theo_truc(edges, truc='y')
    
    # Tìm peaks trong projection → vị trí đường ngang
    # min_distance là khoảng cách tối thiểu giữa 2 đường ngang
    # height_threshold là ngưỡng để coi là đường ngang (dựa trên intensity max)
    
    if target_h_lines is not None:
        # Tự động tìm threshold để đạt target
        print(f"[INFO] Mục tiêu: {target_h_lines} đường NGANG")
        h_threshold, h_peaks = tim_threshold_tu_dong(
            h_projection,
            target_count=target_h_lines,
            min_distance=int(height / 20),
            max_iterations=100
        )
    else:
        # Dùng threshold mặc định
        h_peaks = tim_duong_tu_projection(
            h_projection, 
            min_distance=int(height / 20),                # 5% chiều cao
            height_threshold=np.max(h_projection) * 0.3   # 30% của peak cao nhất
        )
        h_threshold = np.max(h_projection) * 0.3
    
    print(f"[INFO] Phát hiện {len(h_peaks)} đường NGANG tại các vị trí Y:")
    # for idx, y in enumerate(h_peaks):
    #     print(f"  H{idx}: y={y} (intensity={int(h_projection[y])})")
    
    # Tạo danh sách horizontal_lines
    merged_h_lines = []
    for y in h_peaks:
        merged_h_lines.append({
            'y': int(y),
            'x1': 0,
            'x2': width
        })
    
    # 5. PHƯƠNG ÁN 5: Edge Projection cho đường DỌC
    print("[INFO] Bước 4: Chiếu edges theo trục X (tìm đường DỌC)...")
    v_projection = chieu_edge_theo_truc(edges, truc='x')
    
    # Tìm peaks trong projection → vị trí đường dọc
    
    if target_v_lines is not None:
        # Tự động tìm threshold để đạt target
        print(f"[INFO] Mục tiêu: {target_v_lines} đường DỌC")
        v_threshold, v_peaks = tim_threshold_tu_dong(
            v_projection,
            target_count=target_v_lines,
            min_distance=int(width / 8),
            max_iterations=100
        )
    else:
        # Dùng threshold mặc định
        v_peaks = tim_duong_tu_projection(
            v_projection, 
            min_distance=int(width / 8),                # 12.5% chiều rộng
            height_threshold=np.max(v_projection) * 0.4  # 40% của peak cao nhất
        )
        v_threshold = np.max(v_projection) * 0.4
    
    print(f"[INFO] Phát hiện {len(v_peaks)} đường DỌC tại các vị trí X:")
    # for idx, x in enumerate(v_peaks):
    #     print(f"  V{idx}: x={x} (intensity={int(v_projection[x])})")
    
    # Vẽ biểu đồ projection cho cả 2 chiều
    ve_bieu_do_projection(h_projection, v_projection, h_peaks, v_peaks, duong_dan_anh, h_threshold, v_threshold)
    
    # Tạo danh sách vertical_lines
    merged_v_lines = []
    for x in v_peaks:
        merged_v_lines.append({
            'x': int(x),
            'y1': 0,
            'y2': height
        })
    
    # 6. Tạo grid từ giao điểm
    grid = []
    if len(merged_h_lines) >= 2 and len(merged_v_lines) >= 2:
        num_rows = len(merged_h_lines) - 1
        num_cols = len(merged_v_lines) - 1
        
        for i in range(num_rows):
            row_cells = []
            for j in range(num_cols):
                cell = {
                    'row': i,
                    'col': j,
                    'x_min': merged_v_lines[j]['x'],
                    'y_min': merged_h_lines[i]['y'],
                    'x_max': merged_v_lines[j + 1]['x'],
                    'y_max': merged_h_lines[i + 1]['y']
                }
                row_cells.append(cell)
            grid.append(row_cells)
        
        print(f"\n[INFO] Đã tạo grid: {num_rows} dòng x {num_cols} cột")
    
    # 7. Vẽ kết quả lên ảnh
    if hien_thi:
        result_img = img.copy()
        
        # Vẽ đường ngang (màu xanh lá) và ghi label
        for idx, line in enumerate(merged_h_lines):
            cv2.line(result_img, (line['x1'], line['y']), (line['x2'], line['y']), (0, 255, 0), 2)
            
            label = f"H{idx}"
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(result_img, 
                         (5, line['y'] - text_h - 5), 
                         (5 + text_w + 10, line['y'] + 5), 
                         (0, 255, 0), -1)
            cv2.putText(result_img, label, 
                       (10, line['y']), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        # Vẽ đường dọc (màu xanh dương) và ghi label
        for idx, line in enumerate(merged_v_lines):
            cv2.line(result_img, (line['x'], line['y1']), (line['x'], line['y2']), (255, 0, 0), 2)
            
            label = f"V{idx}"
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(result_img, 
                         (line['x'] - text_w//2 - 5, 5), 
                         (line['x'] + text_w//2 + 5, 5 + text_h + 10), 
                         (255, 0, 0), -1)
            cv2.putText(result_img, label, 
                       (line['x'] - text_w//2, 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Vẽ các ô (màu đỏ)
        for row in grid:
            for cell in row:
                cv2.rectangle(result_img, 
                            (cell['x_min'], cell['y_min']), 
                            (cell['x_max'], cell['y_max']), 
                            (0, 0, 255), 1)
                
                text = f"[{cell['row']},{cell['col']}]"
                cv2.putText(result_img, text, 
                          (cell['x_min'] + 5, cell['y_min'] + 20), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
        
        # Lưu ảnh kết quả
        base_name = os.path.splitext(duong_dan_anh)[0]
        ext = os.path.splitext(duong_dan_anh)[1]
        output_path = f"{base_name}_edge_projection{ext}"
        cv2.imwrite(output_path, result_img)
        print(f"\n[INFO] Đã lưu ảnh kết quả: {output_path}")
        
        # Lưu thêm ảnh edges để debug
        edges_output = f"{base_name}_edges{ext}"
        cv2.imwrite(edges_output, edges)
        print(f"[INFO] Đã lưu ảnh edges: {edges_output}")
    
    return {
        'horizontal_lines': merged_h_lines,
        'vertical_lines': merged_v_lines,
        'grid': grid
    }


def phat_hien_grid_phieu_bau(anh, target_h_lines=11, target_v_lines=4, verbose=False):
    """
    Phát hiện grid động cho phiếu bầu (dùng cho tien_xu_ly.py)
    
    Args:
        anh: Ảnh đã được làm phẳng (numpy array từ cv2)
        target_h_lines: Số đường ngang mong muốn (mặc định 11 cho phiếu bầu)
        target_v_lines: Số đường dọc mong muốn (mặc định 4 cho phiếu bầu)
        verbose: In thông tin debug
        
    Returns:
        dict: {'grid': [[cell_dict, ...], ...]} hoặc None nếu thất bại
    """
    try:
        # Chuyển sang grayscale nếu cần
        if len(anh.shape) == 3:
            gray = cv2.cvtColor(anh, cv2.COLOR_BGR2GRAY)
        else:
            gray = anh
        
        height, width = gray.shape
        
        # Tiền xử lý
        enhanced = tien_xu_ly_anh(gray)
        
        # Edge Detection
        edges = cv2.Canny(enhanced, 50, 150, apertureSize=3)
        
        # Projection cho đường NGANG
        h_projection = chieu_edge_theo_truc(edges, truc='y')
        h_threshold, h_peaks = tim_threshold_tu_dong(
            h_projection,
            target_count=target_h_lines,
            min_distance=int(height / 20),
            max_iterations=100
        )
        
        if verbose:
            print(f"[INFO] Phát hiện {len(h_peaks)} đường NGANG (mục tiêu: {target_h_lines})")
        
        # Projection cho đường DỌC
        v_projection = chieu_edge_theo_truc(edges, truc='x')
        v_threshold, v_peaks = tim_threshold_tu_dong(
            v_projection,
            target_count=target_v_lines,
            min_distance=int(width / 8),
            max_iterations=100
        )
        
        if verbose:
            print(f"[INFO] Phát hiện {len(v_peaks)} đường DỌC (mục tiêu: {target_v_lines})")
        
        # Tạo danh sách horizontal_lines
        merged_h_lines = []
        for y in h_peaks:
            merged_h_lines.append({
                'y': int(y),
                'x1': 0,
                'x2': width
            })
        
        # Tạo danh sách vertical_lines
        merged_v_lines = []
        for x in v_peaks:
            merged_v_lines.append({
                'x': int(x),
                'y1': 0,
                'y2': height
            })
        
        # Tạo grid từ giao điểm
        grid = []
        if len(merged_h_lines) >= 2 and len(merged_v_lines) >= 2:
            num_rows = len(merged_h_lines) - 1
            num_cols = len(merged_v_lines) - 1
            
            for i in range(num_rows):
                row_cells = []
                for j in range(num_cols):
                    cell = {
                        'row': i,
                        'col': j,
                        'x_min': merged_v_lines[j]['x'],
                        'y_min': merged_h_lines[i]['y'],
                        'x_max': merged_v_lines[j + 1]['x'],
                        'y_max': merged_h_lines[i + 1]['y']
                    }
                    row_cells.append(cell)
                grid.append(row_cells)
            
            if verbose:
                print(f"[INFO] Đã tạo grid: {num_rows} dòng x {num_cols} cột")
            
            return {
                'grid': grid,
                'horizontal_lines': merged_h_lines,
                'vertical_lines': merged_v_lines
            }
        else:
            if verbose:
                print(f"[ERROR] Không đủ đường kẻ để tạo grid!")
            return None
            
    except Exception as e:
        if verbose:
            print(f"[ERROR] Lỗi phát hiện grid: {e}")
        return None


def cat_cac_o_tu_grid(duong_dan_anh, grid, thu_muc_luu):
    """
    Cắt các ô từ grid đã phát hiện
    
    Args:
        duong_dan_anh: Đường dẫn ảnh gốc
        grid: Grid các ô từ hàm phat_hien_duong_ke()
        thu_muc_luu: Thư mục lưu kết quả
    
    Returns:
        int: Số lượng ô đã cắt
    """
    os.makedirs(thu_muc_luu, exist_ok=True)
    
    img = cv2.imread(duong_dan_anh)
    
    print(f"[INFO] Bắt đầu cắt {len(grid)} dòng x {len(grid[0]) if grid else 0} cột...")
    
    count = 0
    for row in grid:
        for cell in row:
            # Cắt ô
            cropped = img[cell['y_min']:cell['y_max'], cell['x_min']:cell['x_max']]
            
            if cropped.size == 0:
                continue
            
            # Đặt tên file theo định dạng row-col: 00.jpg, 01.jpg, 10.jpg...
            filename = f"{cell['row']}{cell['col']}.jpg"
            filepath = os.path.join(thu_muc_luu, filename)
            
            # Lưu
            cv2.imwrite(filepath, cropped)
            count += 1
    
    print(f"[INFO] Đã cắt {count} ô và lưu vào: {thu_muc_luu}")
    return count


if __name__ == "__main__":
    import sys
    import glob
    
    # Cấu hình mặc định
    input_dir_default = "../data/lam_phang"
    output_dir_default = "../data/anh_da_cat"
    
    # Đọc tham số từ command line
    target_h = None
    target_v = None
    
    if len(sys.argv) >= 2:
        target_h = int(sys.argv[1])
    if len(sys.argv) >= 3:
        target_v = int(sys.argv[2])
    
    # Kiểm tra thư mục input
    input_dir = input_dir_default
    output_dir = output_dir_default
    
    if not os.path.exists(input_dir):
        print(f"❌ Thư mục {input_dir} không tồn tại!")
        print(f"\nCách dùng:")
        print(f"  python cat_noi_dung_tu_bang.py [số_đường_ngang] [số_đường_dọc]")
        print(f"\nVí dụ:")
        print(f"  python cat_noi_dung_tu_bang.py")
        print(f"  python cat_noi_dung_tu_bang.py 12 5")
        sys.exit(1)
    
    # Tạo thư mục output
    os.makedirs(output_dir, exist_ok=True)
    
    # Tìm tất cả file ảnh
    image_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
        image_files.extend(glob.glob(os.path.join(input_dir, ext)))
    
    # Loại bỏ trùng lặp (Windows không phân biệt hoa/thường)
        image_files = list(set(os.path.normpath(f) for f in image_files))
        image_files.sort()  # Sắp xếp để dễ theo dõi

    if not image_files:
        print(f"❌ Không tìm thấy ảnh nào trong {input_dir}")
        sys.exit(1)
    
    print("=" * 70)
    print("PHÁT HIỆN VÀ CẮT NỘI DUNG BẢNG - EDGE PROJECTION")
    print("=" * 70)
    print(f"🔍 Tìm thấy {len(image_files)} ảnh trong {input_dir}")
    print(f"📁 Kết quả sẽ lưu vào: {output_dir}")
    
    if target_h is not None or target_v is not None:
        print(f"[INFO] Chế độ: Tự động điều chỉnh threshold")
        if target_h is not None:
            print(f"[INFO] Mục tiêu đường NGANG: {target_h}")
        if target_v is not None:
            print(f"[INFO] Mục tiêu đường DỌC: {target_v}")
    else:
        print(f"[INFO] Chế độ: Sử dụng threshold mặc định")
    
    print("=" * 70)
    
    success_count = 0
    error_count = 0
    total_cells = 0
    
    for idx, duong_dan_anh in enumerate(image_files, 1):
        try:
            filename = os.path.basename(duong_dan_anh)
            base_name = os.path.splitext(filename)[0]
            
            print(f"\n[{idx}/{len(image_files)}] 📸 Xử lý: {filename}")
            print("-" * 70)
            
            # Phát hiện đường kẻ
            ket_qua = phat_hien_duong_ke_edge_projection(
                duong_dan_anh, 
                hien_thi=True,
                target_h_lines=target_h,
                target_v_lines=target_v
            )
            
            # Kiểm tra kết quả
            # print(f"\n[INFO] Đã phát hiện: {len(ket_qua['horizontal_lines'])} dòng x {len(ket_qua['vertical_lines'])} cột")
            
            if target_h is not None or target_v is not None:
                h_match = "✅" if target_h is None or len(ket_qua['horizontal_lines']) == target_h else "❌"
                v_match = "✅" if target_v is None or len(ket_qua['vertical_lines']) == target_v else "❌"
                
                if target_h is not None:
                    print(f"[INFO] Đường ngang: {len(ket_qua['horizontal_lines'])}/{target_h} {h_match}")
                if target_v is not None:
                    print(f"[INFO] Đường dọc:   {len(ket_qua['vertical_lines'])}/{target_v} {v_match}")
            
            # Tạo thư mục con cho ảnh này
            image_output_dir = os.path.join(output_dir, base_name)
            os.makedirs(image_output_dir, exist_ok=True)
            
            # Cắt các ô
            if ket_qua['grid']:
                cells_count = cat_cac_o_tu_grid(duong_dan_anh, ket_qua['grid'], image_output_dir)
                total_cells += cells_count
                
                # Di chuyển biểu đồ projection vào thư mục con
                base_path = os.path.splitext(duong_dan_anh)[0]
                histogram_file = f"{base_path}_projection_histogram.png"
                if os.path.exists(histogram_file):
                    import shutil
                    shutil.move(histogram_file, os.path.join(image_output_dir, "projection_histogram.png"))
                    print(f"[INFO] Đã di chuyển biểu đồ vào: {image_output_dir}")
                
                # Di chuyển ảnh edge_projection vào thư mục con
                edge_file = f"{base_path}_edge_projection{os.path.splitext(duong_dan_anh)[1]}"
                if os.path.exists(edge_file):
                    shutil.move(edge_file, os.path.join(image_output_dir, "edge_projection.jpg"))
                
                # Di chuyển ảnh edges vào thư mục con
                edges_file = f"{base_path}_edges{os.path.splitext(duong_dan_anh)[1]}"
                if os.path.exists(edges_file):
                    shutil.move(edges_file, os.path.join(image_output_dir, "edges.jpg"))
                
                print(f"✅ Hoàn thành: {filename}")
                success_count += 1
            else:
                print(f"⚠️ Không tạo được grid cho {filename}")
                error_count += 1
                
        except Exception as e:
            print(f"❌ Lỗi: {e}")
            error_count += 1
    
    # Tổng kết
    print("\n" + "=" * 70)
    print("📊 TỔNG KẾT")
    print("=" * 70)
    print(f"✅ Thành công:  {success_count}/{len(image_files)} ảnh")
    print(f"❌ Lỗi:         {error_count}/{len(image_files)} ảnh")
    print(f"📦 Tổng số ô:   {total_cells} ô")
    print(f"📁 Kết quả tại: {os.path.abspath(output_dir)}")
    print("=" * 70)



