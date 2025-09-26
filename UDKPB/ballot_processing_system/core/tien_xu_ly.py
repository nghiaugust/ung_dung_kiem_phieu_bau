import cv2
import numpy as np
import os
import glob

# Biến toàn cục cho layout của các thư mục khác nhau
# Layout cho data1
Y_MIN1, Y_MAX1 = 208, 2225
COL_BOUNDARIES1 = [385, 974, 1233, 1481]

# Layout cho data2
Y_MIN2, Y_MAX2 = 204, 2128
COL_BOUNDARIES2 = [268, 1009, 1339, 1648]

def sharpen_image(image):
    """Làm nét ảnh bằng unsharp masking"""
    kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(image, -1, kernel)
    alpha = 0.7  # Tỷ lệ ảnh gốc
    beta = 0.3   # Tỷ lệ ảnh làm nét
    result = cv2.addWeighted(image, alpha, sharpened, beta, 0)
    return result

def enhance_image_quality(image):
    """Cải thiện chất lượng ảnh"""
    # 1. Khử nhiễu nhẹ
    denoised = cv2.bilateralFilter(image, 9, 75, 75)
    
    # 2. Cải thiện độ tương phản
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    
    # 3. Làm nét
    sharpened = sharpen_image(enhanced)
    return sharpened

def resize_with_padding_high_quality(image, target_size):
    """Resize ảnh giữ tỉ lệ và thêm padding với chất lượng cao cho ô họ tên"""
    h, w = image.shape[:2]
    target_w, target_h = target_size
    
    # Cắt ảnh 5px ở phía trên và phía bên trái
    crop_top = 5 if h > 5 else 0
    crop_left = 5 if w > 5 else 0
    cropped_image = image[crop_top:, crop_left:]
    
    h, w = cropped_image.shape[:2]
    
    # Tính tỉ lệ scale
    scale = min(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    # Chọn interpolation method phù hợp
    if scale > 1:
        interpolation = cv2.INTER_LANCZOS4  # Phóng to
    else:
        interpolation = cv2.INTER_AREA      # Thu nhỏ
    
    # Resize ảnh với chất lượng cao
    resized = cv2.resize(cropped_image, (new_w, new_h), interpolation=interpolation)
    
    # Nếu phóng to, áp dụng cải thiện chất lượng
    if scale > 1.2:
        resized = enhance_image_quality(resized)
    
    # Tạo ảnh với padding trắng
    padded = np.ones((target_h, target_w, 3), dtype=np.uint8) * 255
    
    # Tính vị trí để center ảnh
    x_offset = (target_w - new_w) // 2
    y_offset = (target_h - new_h) // 2
    
    # Đặt ảnh vào center
    if len(resized.shape) == 3:
        padded[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
    else:
        resized_bgr = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
        padded[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized_bgr
    
    return padded

def add_padding_only(image, target_size):
    """Chỉ thêm padding để đạt kích thước mục tiêu cho ô đồng ý/không đồng ý"""
    h, w = image.shape[:2]
    target_w, target_h = target_size
    
    # Cắt ảnh 5px ở phía trên và phía bên trái
    crop_top = 5 if h > 5 else 0
    crop_left = 5 if w > 5 else 0
    cropped_image = image[crop_top:, crop_left:]
    
    h, w = cropped_image.shape[:2]
    
    # Tạo ảnh với padding trắng
    padded = np.ones((target_h, target_w, 3), dtype=np.uint8) * 255
    
    # Tính vị trí để center ảnh
    x_offset = max(0, (target_w - w) // 2)
    y_offset = max(0, (target_h - h) // 2)
    
    # Tính kích thước thực tế
    actual_w = min(w, target_w)
    actual_h = min(h, target_h)
    
    # Đặt ảnh vào center
    if len(cropped_image.shape) == 3:
        padded[y_offset:y_offset+actual_h, x_offset:x_offset+actual_w] = cropped_image[:actual_h, :actual_w]
    else:
        cropped_bgr = cv2.cvtColor(cropped_image, cv2.COLOR_GRAY2BGR)
        padded[y_offset:y_offset+actual_h, x_offset:x_offset+actual_w] = cropped_bgr[:actual_h, :actual_w]
    
    return padded

def estimate_missing_marker(known_points, missing_id):
    """
    Ước lượng vị trí marker bị thiếu dựa trên 3 markers có sẵn
    
    Args:
        known_points: dict - {id: (x, y)} của các markers đã biết
        missing_id: int - ID của marker bị thiếu (0, 1, 2, hoặc 3)
    
    Returns:
        tuple: (x, y) của marker bị thiếu
    """
    # Thứ tự markers: 0=TL, 1=TR, 2=BR, 3=BL
    
    if missing_id == 0:  # Thiếu Top-Left
        # TL = TR + BL - BR
        if 1 in known_points and 2 in known_points and 3 in known_points:
            tr, br, bl = known_points[1], known_points[2], known_points[3]
            tl_x = tr[0] + bl[0] - br[0]
            tl_y = tr[1] + bl[1] - br[1]
            return (tl_x, tl_y)
    
    elif missing_id == 1:  # Thiếu Top-Right
        # TR = TL + BR - BL
        if 0 in known_points and 2 in known_points and 3 in known_points:
            tl, br, bl = known_points[0], known_points[2], known_points[3]
            tr_x = tl[0] + br[0] - bl[0]
            tr_y = tl[1] + br[1] - bl[1]
            return (tr_x, tr_y)
    
    elif missing_id == 2:  # Thiếu Bottom-Right
        # BR = TR + BL - TL
        if 0 in known_points and 1 in known_points and 3 in known_points:
            tl, tr, bl = known_points[0], known_points[1], known_points[3]
            br_x = tr[0] + bl[0] - tl[0]
            br_y = tr[1] + bl[1] - tl[1]
            return (br_x, br_y)
    
    elif missing_id == 3:  # Thiếu Bottom-Left
        # BL = TL + BR - TR
        if 0 in known_points and 1 in known_points and 2 in known_points:
            tl, tr, br = known_points[0], known_points[1], known_points[2]
            bl_x = tl[0] + br[0] - tr[0]
            bl_y = tl[1] + br[1] - tr[1]
            return (bl_x, bl_y)
    
    return None

def straighten_ballot(image_path):
    """Làm phẳng ảnh phiếu bầu dựa trên ArUco markers (hỗ trợ 3-4 markers)"""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Tạo detector cho ArUco markers
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

    # Phát hiện markers
    corners, ids, _ = detector.detectMarkers(gray)

    if ids is None or len(ids) < 3:
        raise ValueError("Cần ít nhất 3 markers để xử lý!")

    ids = ids.flatten()
    pts = {}

    # Lưu tọa độ marker theo id
    for corner, id in zip(corners, ids):
        center = np.mean(corner[0], axis=0)
        pts[id] = center

    # Nếu có đủ 4 markers, xử lý bình thường
    if len(ids) >= 4:
        ordered_pts = np.array([pts[0], pts[1], pts[2], pts[3]], dtype="float32")
    
    # Nếu chỉ có 3 markers, ước lượng marker thứ 4
    elif len(ids) == 3:
        
        # Tìm marker nào bị thiếu
        all_ids = {0, 1, 2, 3}
        missing_id = list(all_ids - set(ids))[0]
        
        # Ước lượng vị trí marker bị thiếu
        estimated_point = estimate_missing_marker(pts, missing_id)
        
        if estimated_point is None:
            raise ValueError(f"Không thể ước lượng marker {missing_id} từ {ids.tolist()}")
        
        pts[missing_id] = estimated_point
        
        # Tạo ordered_pts với marker đã ước lượng
        ordered_pts = np.array([pts[0], pts[1], pts[2], pts[3]], dtype="float32")

    # Kích thước phiếu chuẩn
    width, height = 1654, 2339
    dst_pts = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], dtype="float32")

    # Biến đổi perspective
    M = cv2.getPerspectiveTransform(ordered_pts, dst_pts)
    warped = cv2.warpPerspective(img, M, (width, height))

    return warped

def get_layout1():
    """Trả về layout cho data1 - chỉ lấy 3 cột: tên, đồng ý, không đồng ý"""
    # 11 dòng cao bằng nhau, nhưng chỉ lấy 10 dòng (bỏ header - dòng đầu)
    cell_h1 = (Y_MAX1 - Y_MIN1) / 11
    rows_y1 = []
    for row in range(1, 11):  # Bỏ dòng 0 (header), lấy dòng 1-10
        y1 = int(Y_MIN1 + row * cell_h1)
        y2 = int(Y_MIN1 + (row + 1) * cell_h1)
        rows_y1.append((y1, y2))
    
    # Chỉ lấy 3 cột: họ tên, đồng ý, không đồng ý (bỏ cột STT)
    cols_x1 = []
    for col in range(3):
        x1 = COL_BOUNDARIES1[col]
        x2 = COL_BOUNDARIES1[col + 1]
        cols_x1.append((x1, x2))
    
    layout1 = {}
    for row_idx, (y1, y2) in enumerate(rows_y1, start=1):
        layout1[row_idx] = {}
        for col_idx, (x1, x2) in enumerate(cols_x1):
            if col_idx == 0:
                field = "name"
            elif col_idx == 1:
                field = "agree"
            else:
                field = "disagree"
            layout1[row_idx][field] = (x1, y1, x2, y2)
    
    return layout1

def get_layout2():
    """Trả về layout cho data2 - chỉ lấy 3 cột: tên, đồng ý, không đồng ý"""
    # 11 dòng cao bằng nhau, nhưng chỉ lấy 10 dòng (bỏ header - dòng đầu)
    cell_h2 = (Y_MAX2 - Y_MIN2) / 11
    rows_y2 = []
    for row in range(1, 11):  # Bỏ dòng 0 (header), lấy dòng 1-10
        y1 = int(Y_MIN2 + row * cell_h2)
        y2 = int(Y_MIN2 + (row + 1) * cell_h2)
        rows_y2.append((y1, y2))
    
    # Chỉ lấy 3 cột: họ tên, đồng ý, không đồng ý (bỏ cột STT)
    cols_x2 = []
    for col in range(3):
        x1 = COL_BOUNDARIES2[col]
        x2 = COL_BOUNDARIES2[col + 1]
        cols_x2.append((x1, x2))
    
    layout2 = {}
    for row_idx, (y1, y2) in enumerate(rows_y2, start=1):
        layout2[row_idx] = {}
        for col_idx, (x1, x2) in enumerate(cols_x2):
            if col_idx == 0:
                field = "name"
            elif col_idx == 1:
                field = "agree"
            else:
                field = "disagree"
            layout2[row_idx][field] = (x1, y1, x2, y2)
    
    return layout2

def crop_regions(img, layout, base_filename, output_dir):
    """Cắt các vùng theo layout và lưu ảnh với xử lý khác nhau cho từng loại ô"""
    for row_idx, row_data in layout.items():
        for field, (x1, y1, x2, y2) in row_data.items():
            # Cắt vùng từ ảnh gốc
            cropped = img[y1:y2, x1:x2]
            
            if cropped.size == 0:
                continue
            
            # Xử lý theo từng loại ô
            if field == "name":
                # Ô họ tên: resize với padding chất lượng cao về 384x384
                processed = resize_with_padding_high_quality(cropped, (384, 384))
                filename = f"{base_filename}_row{row_idx:02d}_hoten.jpg"
            elif field == "agree":
                # Ô đồng ý: chỉ thêm padding về 640x640
                processed = add_padding_only(cropped, (640, 640))
                filename = f"{base_filename}_row{row_idx:02d}_dongy.jpg"
            elif field == "disagree":
                # Ô không đồng ý: chỉ thêm padding về 640x640
                processed = add_padding_only(cropped, (640, 640))
                filename = f"{base_filename}_row{row_idx:02d}_khongdongy.jpg"
            else:
                # Các ô khác: giữ nguyên
                processed = cropped
                filename = f"{base_filename}_row{row_idx:02d}_{field}.jpg"
            
            # Lưu ảnh
            filepath = os.path.join(output_dir, filename)
            cv2.imwrite(filepath, processed)
            
            # print(f"  → Đã cắt: {filename}")

def process_all_ballots(input_dirs=None, output_dir=None):
    """Xử lý tất cả phiếu bầu trong các thư mục data1, data2"""
    if input_dirs is None:
        input_dirs = ["ballot/data1", "ballot/data2"]  # Mặc định xử lý cả 2 thư mục
    elif isinstance(input_dirs, str):
        input_dirs = [input_dirs]  # Chuyển string thành list
    
    if output_dir is None:
        output_dir = "results/ket_qua_tien_xu_ly"
    
    # Tạo thư mục output chính
    os.makedirs(output_dir, exist_ok=True)
    
    total_success = 0
    total_files = 0
    all_results = []
    
    for input_dir in input_dirs:
        if not os.path.exists(input_dir):
            print(f"⚠️ Thư mục {input_dir} không tồn tại, bỏ qua...")
            continue
            
        
        # Chọn layout phù hợp dựa trên thư mục input
        if "data1" in input_dir:
            layout = get_layout1()
        elif "data2" in input_dir:
            layout = get_layout2()
        else:
            print(f"⚠️ Thư mục {input_dir} không được hỗ trợ, chỉ hỗ trợ ballot/data1 và ballot/data2")
            continue
        
        # Tạo thư mục con cho từng input_dir
        sub_output_dir = os.path.join(output_dir, f"ket_qua_{os.path.basename(input_dir)}")
        os.makedirs(sub_output_dir, exist_ok=True)
    
        # Tìm tất cả ảnh (loại bỏ trùng lặp)
        image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            image_files.extend(glob.glob(os.path.join(input_dir, ext)))
            image_files.extend(glob.glob(os.path.join(input_dir, ext.upper())))
        
        # Loại bỏ file trùng lặp bằng cách chuyển về đường dẫn chuẩn
        image_files = list(set(os.path.normpath(f) for f in image_files))
        
        if not image_files:
            print(f"❌ Không tìm thấy ảnh nào trong {input_dir}!")
            continue
        
        print(f"🔍 Tìm thấy {len(image_files)} ảnh trong {input_dir}")
        total_files += len(image_files)
        
        success_count = 0
        
        for image_path in image_files:
            try:
                filename = os.path.basename(image_path)
                base_name = os.path.splitext(filename)[0]
                
                print(f"📸 Xử lý: {filename}")
                
                # Bước 1: Làm phẳng ảnh
                straightened_img = straighten_ballot(image_path)
                
                # Lưu ảnh đã làm phẳng
                straightened_path = os.path.join(sub_output_dir, f"{base_name}_straightened.jpg")
                cv2.imwrite(straightened_path, straightened_img)
                print(f"  → Đã làm phẳng: {base_name}_straightened.jpg")
                
                # Bước 2: Cắt theo layout với xử lý chuyên biệt
                crop_regions(straightened_img, layout, base_name, sub_output_dir)
                
                print(f"✅ Hoàn thành: {filename}")
                success_count += 1
                total_success += 1
                all_results.append({
                    'original_path': image_path,
                    'base_name': base_name,
                    'straightened_path': straightened_path,
                    'output_dir': sub_output_dir,
                    'source_folder': input_dir
                })
                
            except Exception as e:
                print(f"❌ Lỗi {filename}: {e}")
        
    return all_results

def xu_ly_phieu_bau(duong_dan_anh, thu_muc_luu="results/ket_qua_tien_xu_ly", layout=None):
    """
    Xử lý một phiếu bầu cụ thể với ArUco markers và layout tùy chọn
    
    Args:
        duong_dan_anh: Đường dẫn tới ảnh phiếu bầu
        thu_muc_luu: Thư mục lưu kết quả
        layout: Layout cụ thể (None để auto-detect)
        
    Returns:
        List[List[Dict]]: Ma trận 2D chứa thông tin các ảnh đã cắt
    """
    # Tạo thư mục lưu kết quả nếu chưa có
    if not os.path.exists(thu_muc_luu):
        os.makedirs(thu_muc_luu)
    
    try:
        filename = os.path.basename(duong_dan_anh)
        base_name = os.path.splitext(filename)[0]
        
        # Bước 1: Làm phẳng ảnh
        straightened_img = straighten_ballot(duong_dan_anh)
        
        # Lưu ảnh đã làm phẳng
        straightened_path = os.path.join(thu_muc_luu, f"{base_name}_straightened.jpg")
        cv2.imwrite(straightened_path, straightened_img)
        
        # Bước 2: Chọn layout phù hợp
        if layout is None:
            # Auto-detect layout dựa trên đường dẫn
            path_lower = duong_dan_anh.lower()
            if "data1" in path_lower:
                layout = get_layout1()
            elif "data2" in path_lower:
                layout = get_layout2()
            else:
                layout = get_layout1() # Mặc định chọn layout1 nếu không xác định được
                print("Không xác định được layout từ đường dẫn, mặc định dùng layout data1.")
                #raise ValueError("Không thể xác định layout. Chỉ hỗ trợ ballot/data1 và ballot/data2. Vui lòng truyền layout cụ thể.")
        
        # Bước 3: Cắt theo layout đã chọn
        ket_qua_cat_anh = []
        
        for row_idx, row_data in layout.items():
            danh_sach_o_trong_dong = []
            
            for field, (x1, y1, x2, y2) in row_data.items():
                # Cắt vùng từ ảnh gốc
                cropped = straightened_img[y1:y2, x1:x2]
                
                if cropped.size == 0:
                    continue
                
                # Xử lý theo từng loại ô
                if field == "name":
                    processed = resize_with_padding_high_quality(cropped, (384, 384))
                    filename_part = f"{base_name}_row{row_idx:02d}_hoten.jpg"
                    loai = "hoten"
                elif field == "agree":
                    processed = add_padding_only(cropped, (640, 640))
                    filename_part = f"{base_name}_row{row_idx:02d}_dongy.jpg"
                    loai = "dongy"
                elif field == "disagree":
                    processed = add_padding_only(cropped, (640, 640))
                    filename_part = f"{base_name}_row{row_idx:02d}_khongdongy.jpg"
                    loai = "khongdongy"
                else:
                    processed = cropped
                    filename_part = f"{base_name}_row{row_idx:02d}_{field}.jpg"
                    loai = field
                
                # Lưu ảnh
                filepath = os.path.join(thu_muc_luu, filename_part)
                cv2.imwrite(filepath, processed)
                
                danh_sach_o_trong_dong.append({
                    'anh': processed,
                    'duong_dan': filepath,
                    'loai': loai
                })
                
                # print(f"  → Đã cắt: {filename_part}")
            
            if danh_sach_o_trong_dong:
                ket_qua_cat_anh.append(danh_sach_o_trong_dong)
        
        print(f"✅ Hoàn thành: {filename} - Cắt được {len(ket_qua_cat_anh)} dòng")
        return ket_qua_cat_anh
        
    except Exception as e:
        print(f"❌ Lỗi xử lý {duong_dan_anh}: {e}")
        return None

if __name__ == "__main__":
    process_all_ballots()
