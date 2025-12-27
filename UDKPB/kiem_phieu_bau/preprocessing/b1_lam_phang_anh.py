"""
Module làm phẳng ảnh phiếu bầu dựa trên ArUco markers
Yêu cầu 4 markers để xử lý
"""

import cv2
import numpy as np
import sys
import os

# Import detect_qr_codes từ ballot.doc_qr
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ballot.doc_qr import detect_qr_codes


def detect_qr_code(image, gray_image=None):
    """
    Phát hiện QR code bằng QReader (từ doc_qr.py)
    
    Args:
        image: Ảnh màu (BGR)
        gray_image: Ảnh grayscale (không sử dụng, chỉ để tương thích API)
    
    Returns:
        tuple: (qr_data, qr_corners) hoặc (None, None) nếu không tìm thấy
        - qr_data: str - Dữ liệu decode được
        - qr_corners: numpy array shape (4, 2) - 4 góc của QR code
    """
    try:
        # Dùng detect_qr_codes từ doc_qr (QReader)
        qr_results = detect_qr_codes(image)
        
        if qr_results and len(qr_results) > 0:
            # Lấy QR code đầu tiên
            qr = qr_results[0]
            qr_data = qr.get('data')
            
            # Trích xuất corners từ polygon
            if 'polygon' in qr and qr['polygon']:
                # polygon là list[(x, y), ...]
                qr_corners = np.array(qr['polygon'], dtype=np.float32)
                return qr_data, qr_corners
            
            # Nếu không có polygon, tạo từ rect
            if 'rect' in qr:
                rect = qr['rect']
                left = rect['left']
                top = rect['top']
                right = left + rect['width']
                bottom = top + rect['height']
                
                # Tạo 4 góc: TL, TR, BR, BL
                qr_corners = np.array([
                    [left, top],
                    [right, top],
                    [right, bottom],
                    [left, bottom]
                ], dtype=np.float32)
                
                return qr_data, qr_corners
    except Exception as e:
        print(f"[WARNING] QReader failed: {e}")
    
    return None, None


def lam_phang_anh(duong_dan_anh_dau_vao, duong_dan_anh_dau_ra, chieu_ngang_cm, chieu_doc_cm, dpi=300):
    """
    Làm phẳng ảnh phiếu bầu dựa trên ArUco markers (yêu cầu đủ 4 markers)
    
    Args:
        duong_dan_anh_dau_vao: str - Đường dẫn tới ảnh đầu vào
        duong_dan_anh_dau_ra: str - Đường dẫn lưu ảnh đầu ra (đã làm phẳng)
        chieu_ngang_cm: float - Khoảng cách ngang giữa các markers (cm)
        chieu_doc_cm: float - Khoảng cách dọc giữa các markers (cm)
        dpi: int - DPI để chuyển đổi cm sang pixel (mặc định 300)
        
    Returns:
        numpy.ndarray: Ảnh đã làm phẳng
        
    Raises:
        ValueError: Nếu không tìm thấy đủ 4 markers hoặc không đọc được ảnh
        
    Note:
        - ID 0: QR Code (Top-Left) - Lấy góc bottom-right
        - Marker 1: ArUco Top-Right - Lấy góc bottom-left
        - Marker 2: ArUco Bottom-Right - Lấy góc top-left
        - Marker 3: ArUco Bottom-Left - Lấy góc top-right
        - Khoảng cách tính từ GÓC (không phải tâm)
        - DPI 300: 1 cm = 118.11 pixels
    """
    # Chuyển đổi cm sang pixel
    # 1 inch = 2.54 cm, 1 inch = dpi pixels => 1 cm = dpi / 2.54 pixels
    pixels_per_cm = dpi / 2.54
    chieu_rong_pixel = int(chieu_ngang_cm * pixels_per_cm)
    chieu_dai_pixel = int(chieu_doc_cm * pixels_per_cm)
    
    print(f"[INFO] Chuyển đổi kích thước: {chieu_ngang_cm}cm x {chieu_doc_cm}cm -> {chieu_rong_pixel}px x {chieu_dai_pixel}px (DPI: {dpi})")
    
    # Đọc ảnh đầu vào
    img = cv2.imread(duong_dan_anh_dau_vao)
    if img is None:
        raise ValueError(f"Không thể đọc ảnh từ: {duong_dan_anh_dau_vao}")
    
    h, w = img.shape[:2]
    
    # Chia ảnh làm 4 phần (từ tâm)
    mid_h, mid_w = h // 2, w // 2
    
    # Tạo detector cho ArUco markers
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    
    # Dictionary lưu góc markers theo id
    marker_corners = {}
    
    # Định nghĩa 4 vùng quét và marker dự kiến
    regions = [
        # (y_start, y_end, x_start, x_end, expected_marker_id, corner_index, offset_y, offset_x, use_qr)
        (0, mid_h, 0, mid_w, 0, 2, 0, 0, True),              # Top-Left quadrant -> QR Code, góc bottom-right
        (0, mid_h, mid_w, w, 1, 3, 0, mid_w, False),         # Top-Right quadrant -> Marker 1, góc bottom-left
        (mid_h, h, mid_w, w, 2, 0, mid_h, mid_w, False),     # Bottom-Right quadrant -> Marker 2, góc top-left
        (mid_h, h, 0, mid_w, 3, 1, mid_h, 0, False)          # Bottom-Left quadrant -> Marker 3, góc top-right
    ]
    
    print(f"[INFO] Bắt đầu quét 4 vùng (QR + 3 markers)...")
    
    for y_start, y_end, x_start, x_end, expected_id, corner_idx, offset_y, offset_x, use_qr in regions:
        # Cắt vùng
        region = img[y_start:y_end, x_start:x_end]
        gray_region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        
        if use_qr:
            # Phát hiện QR Code bằng QReader
            qr_data, qr_corners = detect_qr_code(region, gray_region)
            
            # Tìm QR code đầu tiên
            qr_found = False
            scale_factor = 1.0  # Hệ số scale (1.0 = không scale)
            
            if qr_data and qr_corners is not None:
                # Tinh chỉnh sub-pixel cho góc QR
                criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                corners_refined = cv2.cornerSubPix(
                    gray_region,
                    qr_corners.reshape(-1, 1, 2),
                    winSize=(5, 5),
                    zeroZone=(-1, -1),
                    criteria=criteria
                )
                qr_corners = corners_refined.reshape(4, 2)
                
                # Lấy góc bottom-right của QR
                # OpenCV trả về góc theo thứ tự: TL, TR, BR, BL
                # Tìm góc có tổng (x + y) lớn nhất = bottom-right
                corner_sums = qr_corners[:, 0] + qr_corners[:, 1]
                br_idx = np.argmax(corner_sums)
                corner_point = qr_corners[br_idx]
                
                # Quy đổi tọa độ về ảnh gốc
                corner_point_global = corner_point + np.array([offset_x, offset_y])
                
                marker_corners[expected_id] = corner_point_global
                
                print(f"[INFO] Tìm thấy QR Code (ID 0) tại góc bottom-right: ({corner_point_global[0]:.3f}, {corner_point_global[1]:.3f})")
                print(f"[INFO] QR Data: {qr_data}")
                qr_found = True
            
            # Nếu không tìm thấy, thử upscale 3x
            if not qr_found:
                print(f"[INFO] Không tìm thấy QR ở độ phân giải gốc, thử upscale 3x...")
                
                # Upscale ảnh 3x
                region_upscaled = cv2.resize(region, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
                gray_region_upscaled = cv2.cvtColor(region_upscaled, cv2.COLOR_BGR2GRAY)
                scale_factor = 3.0
                
                # Thử decode lại với QReader
                qr_data, qr_corners = detect_qr_code(region_upscaled, gray_region_upscaled)
                
                if qr_data and qr_corners is not None:
                    # Tinh chỉnh sub-pixel
                    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                    corners_refined = cv2.cornerSubPix(
                        gray_region_upscaled,
                        qr_corners.reshape(-1, 1, 2),
                        winSize=(5, 5),
                        zeroZone=(-1, -1),
                        criteria=criteria
                    )
                    qr_corners = corners_refined.reshape(4, 2)
                    
                    # Chuyển tọa độ về ảnh gốc (chia cho scale_factor)
                    qr_corners = qr_corners / scale_factor
                    
                    # Lấy góc bottom-right
                    corner_sums = qr_corners[:, 0] + qr_corners[:, 1]
                    br_idx = np.argmax(corner_sums)
                    corner_point = qr_corners[br_idx]
                    
                    # Quy đổi tọa độ về ảnh gốc
                    corner_point_global = corner_point + np.array([offset_x, offset_y])
                    
                    marker_corners[expected_id] = corner_point_global
                    
                    print(f"[INFO] Tìm thấy QR Code (ID 0) sau upscale 3x tại góc bottom-right: ({corner_point_global[0]:.3f}, {corner_point_global[1]:.3f})")
                    print(f"[INFO] QR Data: {qr_data}")
                    qr_found = True
            
            # Nếu vẫn không tìm thấy, thử upscale 5x
            if not qr_found:
                print(f"[INFO] Không tìm thấy QR sau upscale 3x, thử upscale 5x...")
                
                # Upscale ảnh 5x
                region_upscaled = cv2.resize(region, None, fx=5.0, fy=5.0, interpolation=cv2.INTER_CUBIC)
                gray_region_upscaled = cv2.cvtColor(region_upscaled, cv2.COLOR_BGR2GRAY)
                scale_factor = 5.0
                
                # Thử decode lại với QReader
                qr_data, qr_corners = detect_qr_code(region_upscaled, gray_region_upscaled)
                
                if qr_data and qr_corners is not None:
                    # Tinh chỉnh sub-pixel
                    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                    corners_refined = cv2.cornerSubPix(
                        gray_region_upscaled,
                        qr_corners.reshape(-1, 1, 2),
                        winSize=(5, 5),
                        zeroZone=(-1, -1),
                        criteria=criteria
                    )
                    qr_corners = corners_refined.reshape(4, 2)
                    
                    # Chuyển tọa độ về ảnh gốc (chia cho scale_factor)
                    qr_corners = qr_corners / scale_factor
                    
                    # Lấy góc bottom-right
                    corner_sums = qr_corners[:, 0] + qr_corners[:, 1]
                    br_idx = np.argmax(corner_sums)
                    corner_point = qr_corners[br_idx]
                    
                    # Quy đổi tọa độ về ảnh gốc
                    corner_point_global = corner_point + np.array([offset_x, offset_y])
                    
                    marker_corners[expected_id] = corner_point_global
                    
                    print(f"[INFO] Tìm thấy QR Code (ID 0) sau upscale 5x tại góc bottom-right: ({corner_point_global[0]:.3f}, {corner_point_global[1]:.3f})")
                    print(f"[INFO] QR Data: {qr_data}")
                    qr_found = True
            
            if not qr_found:
                print(f"[WARNING] Không tìm thấy QR Code trong vùng Top-Left (đã thử upscale 3x và 5x)")
        else:
            # Phát hiện ArUco markers (1, 2, 3)
            corners, ids, _ = detector.detectMarkers(gray_region)
            
            if ids is not None:
                for corner, marker_id in zip(corners, ids.flatten()):
                    if marker_id == expected_id:
                        # Lấy 4 góc của marker (theo thứ tự: TL, TR, BR, BL)
                        marker_corners_local = corner[0].copy()
                        
                        # Tinh chỉnh sub-pixel cho tất cả 4 góc của marker
                        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                        
                        corners_refined = cv2.cornerSubPix(
                            gray_region,
                            marker_corners_local.reshape(-1, 1, 2),
                            winSize=(5, 5),
                            zeroZone=(-1, -1),
                            criteria=criteria
                        )
                        
                        marker_corners_local = corners_refined.reshape(4, 2)
                        
                        # Chọn góc phù hợp:
                        # - Marker 1 (TR): lấy góc bottom-left (index 3)
                        # - Marker 2 (BR): lấy góc top-left (index 0)
                        # - Marker 3 (BL): lấy góc top-right (index 1)
                        corner_point = marker_corners_local[corner_idx]
                        
                        # Quy đổi tọa độ về ảnh gốc
                        corner_point_global = corner_point + np.array([offset_x, offset_y])
                        
                        marker_corners[marker_id] = corner_point_global
                        print(f"[INFO] Tìm thấy marker {marker_id} tại góc {corner_idx}: ({corner_point_global[0]:.3f}, {corner_point_global[1]:.3f})")
                        break
    
    # Kiểm tra đủ 4 điểm (1 QR + 3 markers)
    if len(marker_corners) < 4:
        found_ids = sorted(marker_corners.keys())
        missing_ids = [i for i in range(4) if i not in marker_corners]
        raise ValueError(f"Cần đủ 4 điểm tham chiếu! Tìm thấy {len(marker_corners)}: {found_ids}. Thiếu: {missing_ids}")
    
    print(f"[INFO] Tìm thấy đủ 4 điểm tham chiếu (QR + 3 markers): {sorted(marker_corners.keys())}")
    
    # Tạo source points (góc markers trên ảnh gốc)
    src_pts = np.array([
        marker_corners[0],  # Top-Left
        marker_corners[1],  # Top-Right
        marker_corners[2],  # Bottom-Right
        marker_corners[3]   # Bottom-Left
    ], dtype="float32")
    
    # Thêm padding cả 4 phía để không cắt vào nội dung
    padding = 50
    chieu_rong_pixel_with_padding = chieu_rong_pixel + 2 * padding
    chieu_dai_pixel_with_padding = chieu_dai_pixel + 2 * padding
    
    # Tạo destination points
    dst_pts = np.array([
        [padding, padding],                                          # Top-Left
        [chieu_rong_pixel + padding - 1, padding],                   # Top-Right
        [chieu_rong_pixel + padding - 1, chieu_dai_pixel + padding - 1], # Bottom-Right
        [padding, chieu_dai_pixel + padding - 1]                     # Bottom-Left
    ], dtype="float32")
    
    print(f"[INFO] Kích thước đầu ra (với padding 20px): {chieu_rong_pixel_with_padding} x {chieu_dai_pixel_with_padding} pixels")
    
    # Biến đổi perspective
    M = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(img, M, (chieu_rong_pixel_with_padding, chieu_dai_pixel_with_padding))
    
    # Lưu ảnh đầu ra
    success = cv2.imwrite(duong_dan_anh_dau_ra, warped)
    if not success:
        raise ValueError(f"Không thể lưu ảnh tại: {duong_dan_anh_dau_ra}")
    
    print(f"[INFO] Đã lưu ảnh làm phẳng tại: {duong_dan_anh_dau_ra}")
    
    return warped


# Alias cho tương thích với tên hàm cũ
straighten_ballot = lam_phang_anh
