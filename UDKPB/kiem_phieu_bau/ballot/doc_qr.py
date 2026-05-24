"""
Module đọc QR code và ArUco markers từ ảnh phiếu bầu
"""
import cv2
import numpy as np
import json
import os
import sys

GLOBAL_QREADER = None
QREADER_LOAD_ATTEMPTED = False

SHARED_ARUCO_ID = 17


def _env_bool(name, default=True):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_qreader():
    """
    Lazy-load QReader only when server-side QR fallback is actually needed.
    Loading it at Django import time slows down container startup significantly.
    """
    global GLOBAL_QREADER, QREADER_LOAD_ATTEMPTED

    if not _env_bool("ENABLE_QREADER", True):
        return None

    if QREADER_LOAD_ATTEMPTED:
        return GLOBAL_QREADER

    QREADER_LOAD_ATTEMPTED = True
    try:
        from qreader import QReader

        GLOBAL_QREADER = QReader(model_size='s', min_confidence=0.5)
    except Exception as e:
        print(f"⚠️ Không thể tải QReader: {e}")
        GLOBAL_QREADER = None

    return GLOBAL_QREADER


def _normalize_quad_points(points):
    """Return 4 image points as a simple list, or [] when unusable."""
    if points is None:
        return []

    try:
        quad = np.array(points, dtype=np.float32).reshape(-1, 2)
    except Exception:
        return []

    if quad.shape[0] < 4:
        return []

    quad = quad[:4]
    return [(int(round(x)), int(round(y))) for x, y in quad]


def _extract_qreader_polygon(detection):
    """QReader versions expose the QR quadrilateral under different keys."""
    for key in ('quad_xy', 'polygon_xy', 'quad', 'polygon', 'points'):
        if key not in detection:
            continue

        polygon = _normalize_quad_points(detection.get(key))
        if polygon:
            return polygon

    return []


def build_marker_box_from_corners(corners, marker_id=None):
    """Tạo bounding box + tâm từ 4 góc marker."""
    corners = np.array(corners, dtype=np.float32)
    min_x = int(np.min(corners[:, 0]))
    max_x = int(np.max(corners[:, 0]))
    min_y = int(np.min(corners[:, 1]))
    max_y = int(np.max(corners[:, 1]))

    return {
        'left': min_x,
        'right': max_x,
        'top': min_y,
        'bottom': max_y,
        'center_x': (min_x + max_x) / 2.0,
        'center_y': (min_y + max_y) / 2.0,
        'id': marker_id,
        'corners': corners.tolist(),
    }


def detect_aruco_marker_boxes(image, refine_subpixel=False):
    """Detect tất cả ArUco markers và trả về danh sách bounding boxes (không mất marker trùng ID)."""
    gray = image
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    aruco_params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)
    corners, ids, _ = detector.detectMarkers(gray)

    boxes = []
    if ids is None:
        return boxes

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    for corner, marker_id in zip(corners, ids.flatten()):
        marker_corners = corner[0].copy()
        if refine_subpixel:
            refined = cv2.cornerSubPix(
                gray,
                marker_corners.reshape(-1, 1, 2),
                winSize=(5, 5),
                zeroZone=(-1, -1),
                criteria=criteria
            )
            marker_corners = refined.reshape(4, 2)

        boxes.append(build_marker_box_from_corners(marker_corners, marker_id=int(marker_id)))

    return boxes


def detect_shared_aruco_marker_corners(image, shared_id=SHARED_ARUCO_ID, refine_subpixel=True):
    """Detect các ArUco marker có cùng ID và trả về list corners shape (4, 2)."""
    gray = image
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    aruco_params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)
    corners, ids, _ = detector.detectMarkers(gray)

    shared_markers = []
    if ids is None:
        return shared_markers

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    for corner, marker_id in zip(corners, ids.flatten()):
        if int(marker_id) != int(shared_id):
            continue

        marker_corners = corner[0].copy()
        if refine_subpixel:
            refined = cv2.cornerSubPix(
                gray,
                marker_corners.reshape(-1, 1, 2),
                winSize=(5, 5),
                zeroZone=(-1, -1),
                criteria=criteria
            )
            marker_corners = refined.reshape(4, 2)

        shared_markers.append(marker_corners)

    return shared_markers


def classify_shared_markers_from_corners(shared_markers_corners, qr_point):
    """Phân loại 3 marker dùng chung ID thành top-right/bottom-right/bottom-left từ corners."""
    if len(shared_markers_corners) < 3:
        return None

    qr_x = float(qr_point[0])
    marker_meta = []
    for corners in shared_markers_corners:
        marker_meta.append({
            'corners': corners,
            'center_x': float(np.mean(corners[:, 0])),
            'center_y': float(np.mean(corners[:, 1]))
        })

    # The QR point passed here should be the QR center. Pick the top marker by Y,
    # then split the two bottom markers by X to avoid swapping BL/BR on skewed photos.
    top_candidates = [m for m in marker_meta if m['center_x'] > qr_x]
    if top_candidates:
        top_right_marker = min(top_candidates, key=lambda m: (m['center_y'], -m['center_x']))
    else:
        top_right_marker = min(marker_meta, key=lambda m: (m['center_y'], -m['center_x']))

    remaining = [m for m in marker_meta if m is not top_right_marker]
    if len(remaining) < 2:
        return None

    bottom_left_marker = min(remaining, key=lambda m: m['center_x'])
    bottom_right_marker = max(remaining, key=lambda m: m['center_x'])

    if bottom_left_marker is bottom_right_marker:
        return None

    return {
        1: top_right_marker['corners'][3],
        2: bottom_right_marker['corners'][0],
        3: bottom_left_marker['corners'][1],
    }


def classify_shared_aruco_markers(marker_boxes, top_left_box):
    """Phân loại 3 marker dùng chung ID thành TR/BR/BL dựa vào QR (top-left)."""
    if len(marker_boxes) < 3 or top_left_box is None:
        return None, None, None

    qr_center_x = top_left_box['center_x']
    indexed_boxes = list(enumerate(marker_boxes))

    top_candidates = [(idx, box) for idx, box in indexed_boxes if box['center_x'] > qr_center_x]
    if top_candidates:
        tr_idx, top_right = min(top_candidates, key=lambda item: (item[1]['center_y'], -item[1]['center_x']))
    else:
        tr_idx, top_right = min(indexed_boxes, key=lambda item: (item[1]['center_y'], -item[1]['center_x']))

    bottom_candidates = [(idx, box) for idx, box in indexed_boxes if idx != tr_idx]
    if len(bottom_candidates) < 2:
        return None, None, None

    _, bottom_left = min(bottom_candidates, key=lambda item: item[1]['center_x'])
    _, bottom_right = max(bottom_candidates, key=lambda item: item[1]['center_x'])

    return top_right, bottom_right, bottom_left

def detect_aruco_markers(image):
    """
    Detect ArUco markers trong ảnh
    
    Args:
        image: Ảnh đầu vào (numpy array)
    
    Returns:
        dict: Thông tin các ArUco markers tìm thấy
    """
    # Khởi tạo ArUco dictionary
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    aruco_params = cv2.aruco.DetectorParameters()
    
    # Detect markers
    detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)
    corners, ids, rejected = detector.detectMarkers(image)
    
    markers_info = {}
    
    occurrence_count = {}

    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            marker_id = int(marker_id)
            corner = corners[i][0]
            # Tính tọa độ trung tâm
            center_x = int(np.mean(corner[:, 0]))
            center_y = int(np.mean(corner[:, 1]))
            
            # Tính kích thước marker
            width = int(np.linalg.norm(corner[1] - corner[0]))
            height = int(np.linalg.norm(corner[2] - corner[1]))
            
            # Giữ đủ marker khi có nhiều marker trùng cùng 1 ID (ví dụ: 3 marker đều ID 17)
            count = occurrence_count.get(marker_id, 0)
            occurrence_count[marker_id] = count + 1
            key = marker_id if count == 0 else marker_id * 100 + count

            markers_info[key] = {
                'id': marker_id,
                'center': (center_x, center_y),
                'corners': corner.tolist(),
                'size': (width, height)
            }
    
    return markers_info


def detect_qr_codes(image):
    """
    Hàm phụ trợ: Detect QR codes an toàn, xử lý lỗi bộ nhớ numpy
    """
    qr_codes = []
    
    # 1. Kiểm tra ảnh rỗng an toàn (Fix lỗi Truth value)
    if image is None or image.size == 0:
        return []

    try:
        qreader = get_qreader()
        if qreader:
            # 2. Chuẩn hóa ảnh cho QReader (Fix lỗi QReader crash)
            # Chuyển sang RGB
            if len(image.shape) == 3 and image.shape[2] == 3:
                rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                rgb_image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
            
            # QUAN TRỌNG: Sắp xếp lại bộ nhớ đệm để tránh lỗi crash C++ bên dưới
            rgb_image = np.ascontiguousarray(rgb_image, dtype=np.uint8)

            # 3. Detect
            decoded_data = qreader.detect_and_decode(image=rgb_image, return_detections=True)
            
            # 4. Parse kết quả
            if decoded_data and len(decoded_data) == 2:
                texts, detections = decoded_data
                if texts:
                    for text, detection in zip(texts, detections):
                        if text is None: continue
                        
                        str_text = str(text)
                        if not str_text.strip(): continue

                        # Lấy tọa độ
                        bbox = detection.get('bbox_xyxy', [0, 0, 0, 0])
                        l, t, r, b = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
                        polygon = _extract_qreader_polygon(detection)
                        
                        qr_info = {
                            'type': 'QRCODE',
                            'data': str_text,
                            'rect': {'left': l, 'top': t, 'width': r-l, 'height': b-t},
                            'polygon': polygon,
                            'confidence': float(detection.get('confidence', 1.0))
                        }
                        
                        # Thử parse JSON
                        try:
                            qr_info['parsed_data'] = json.loads(str_text)
                        except:
                            pass
                            
                        qr_codes.append(qr_info)
    except Exception as e:
        print(f"⚠️ Lỗi trong detect_qr_codes: {e}")
    
    return qr_codes

def _create_qr_info_from_cv2(data, points, scale=1.0):
    """
    Tạo dictionary thông tin QR code từ kết quả của cv2.QRCodeDetector
    
    Args:
        data: Dữ liệu đã decode (string)
        points: Array các điểm góc từ OpenCV (shape: (4, 2) hoặc (1, 4, 2))
        scale: Hệ số scale nếu ảnh đã được resize
    
    Returns:
        dict: Thông tin QR code
    """
    qr_info = {
        'type': 'QRCODE',
        'data': data,
        'rect': {},
        'polygon': []
    }
    
    # Xử lý points
    if points is not None and len(points) > 0:
        # Flatten points nếu cần
        if len(points.shape) == 3:
            points = points[0]
        
        points = points.astype(int)
        
        # Tính bounding rect
        x_coords = points[:, 0]
        y_coords = points[:, 1]
        
        left = int(np.min(x_coords))
        top = int(np.min(y_coords))
        right = int(np.max(x_coords))
        bottom = int(np.max(y_coords))
        
        qr_info['rect'] = {
            'left': left,
            'top': top,
            'width': right - left,
            'height': bottom - top
        }
        
        # Polygon
        qr_info['polygon'] = [(int(p[0]), int(p[1])) for p in points]
    
    # Thử parse JSON nếu có thể
    try:
        parsed_data = json.loads(data)
        qr_info['parsed_data'] = parsed_data
    except:
        pass
    
    return qr_info

def read_qr_code_only(image_path):
    """
    Chỉ đọc QR code từ ảnh phiếu bầu (không đọc ArUco markers)
    
    Args:
        image_path (str): Đường dẫn đến file ảnh
    
    Returns:
        dict: Thông tin QR codes
        {
            'success': bool,
            'qr_count': int,
            'qr_codes': list,
            'error': str (optional)
        }
    """
    # Đọc ảnh
    image = cv2.imread(image_path)
    
    if image is None:
        return {
            'success': False,
            'error': f'Không thể đọc ảnh từ: {image_path}',
            'qr_count': 0,
            'qr_codes': []
        }
    
    try:
        # Detect QR codes
        qr_codes = detect_qr_codes(image)
        
        return {
            'success': True,
            'qr_count': len(qr_codes),
            'qr_codes': qr_codes
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'qr_count': 0,
            'qr_codes': []
        }


def read_ballot_markers(image_path):
    """
    Đọc tất cả markers (ArUco + QR) từ ảnh phiếu bầu
    
    Args:
        image_path (str): Đường dẫn đến file ảnh
    
    Returns:
        dict: Thông tin tất cả markers
    """
    # Đọc ảnh
    image = cv2.imread(image_path)
    
    if image is None:
        return {
            'error': f'Không thể đọc ảnh từ: {image_path}',
            'aruco_markers': {},
            'qr_codes': []
        }
    
    # Convert sang grayscale cho ArUco detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Detect ArUco markers
    aruco_markers = detect_aruco_markers(gray)
    
    # Detect QR codes
    qr_codes = detect_qr_codes(image)
    
    # Tổng hợp kết quả
    result = {
        'image_path': image_path,
        'image_size': {
            'width': image.shape[1],
            'height': image.shape[0]
        },
        'aruco_markers': aruco_markers,
        'aruco_count': len(aruco_markers),
        'qr_codes': qr_codes,
        'qr_count': len(qr_codes)
    }
    
    return result


def print_marker_info(result):
    """
    In thông tin markers ra terminal một cách đẹp mắt
    
    Args:
        result (dict): Kết quả từ read_ballot_markers
    """
    print("\n" + "="*80)
    print("THÔNG TIN ĐỌC ĐƯỢC TỪ PHIẾU BẦU")
    print("="*80)
    
    # Thông tin ảnh
    print(f"\n📄 File: {result['image_path']}")
    print(f"📐 Kích thước: {result['image_size']['width']}x{result['image_size']['height']} pixels")
    
    # ArUco Markers
    print(f"\n🔲 ArUco Markers: {result['aruco_count']} marker(s) tìm thấy")
    if result['aruco_markers']:
        for marker_id, info in sorted(result['aruco_markers'].items()):
            position_map = {
                0: "Top-left (hoặc QR nếu có signature)",
                1: "Top-right",
                2: "Bottom-right",
                3: "Bottom-left"
            }
            position_name = position_map.get(marker_id, "Unknown")
            
            print(f"\n  Marker ID {marker_id} - {position_name}")
            
            # In vị trí 4 góc
            corners = info['corners']
            print(f"    Góc trên trái:   ({int(corners[0][0])}, {int(corners[0][1])})")
            print(f"    Góc trên phải:   ({int(corners[1][0])}, {int(corners[1][1])})")
            print(f"    Góc dưới phải:   ({int(corners[2][0])}, {int(corners[2][1])})")
            print(f"    Góc dưới trái:   ({int(corners[3][0])}, {int(corners[3][1])})")
            print(f"    Kích thước: {info['size'][0]}x{info['size'][1]} pixels")
    else:
        print("  ❌ Không tìm thấy ArUco marker nào")
    
    # QR Codes
    print(f"\n📱 QR Codes: {result['qr_count']} code(s) tìm thấy")
    if result['qr_codes']:
        for i, qr in enumerate(result['qr_codes'], 1):
            print(f"\n  QR Code #{i}")
            print(f"    Loại: {qr['type']}")
            print(f"    Vị trí: ({qr['rect']['left']}, {qr['rect']['top']})")
            print(f"    Kích thước: {qr['rect']['width']}x{qr['rect']['height']} pixels")
            
            if 'parsed_data' in qr:
                print(f"\n    📋 Dữ liệu (JSON):")
                # In JSON đẹp
                json_str = json.dumps(qr['parsed_data'], indent=6, ensure_ascii=False)
                for line in json_str.split('\n'):
                    print(f"    {line}")
                
                # Phân tích dữ liệu nếu có cấu trúc đặc biệt
                if 'marker_id' in qr['parsed_data']:
                    print(f"\n    ✅ Marker ID: {qr['parsed_data']['marker_id']}")
                
                if 'data' in qr['parsed_data']:
                    data = qr['parsed_data']['data']
                    if 'payload' in data:
                        payload = data['payload']
                        print(f"\n    📦 Payload:")
                        print(f"       Poll ID: {payload.get('poll_id', 'N/A')}")
                        print(f"       Ballot ID: {payload.get('ballot_id', 'N/A')}")
                        print(f"       Timestamp: {payload.get('timestamp', 'N/A')}")
                        print(f"       Salt: {payload.get('salt', 'N/A')}")
                    
                    if 'signature' in data:
                        sig = data['signature']
                        print(f"\n    🔐 Signature: {sig[:50]}..." if len(sig) > 50 else f"\n    🔐 Signature: {sig}")
            else:
                print(f"\n    📝 Dữ liệu (raw): {qr['data']}")
    else:
        print("  ❌ Không tìm thấy QR code nào")
    
    # Kiểm tra lỗi
    if 'error' in result:
        print(f"\n❌ LỖI: {result['error']}")
    
    print("\n" + "="*80 + "\n")


def visualize_markers(image_path, result, output_path=None):
    """
    Vẽ các markers lên ảnh để visualize
    
    Args:
        image_path (str): Đường dẫn ảnh gốc
        result (dict): Kết quả từ read_ballot_markers
        output_path (str): Đường dẫn lưu ảnh output (None = hiển thị)
    """
    # Đọc ảnh
    image = cv2.imread(image_path)
    if image is None:
        print(f"Không thể đọc ảnh: {image_path}")
        return
    
    # Vẽ ArUco markers
    for marker_id, info in result['aruco_markers'].items():
        corners = np.array(info['corners'], dtype=np.int32)
        cv2.polylines(image, [corners], True, (0, 255, 0), 3)
        
        # Vẽ ID
        center = info['center']
        cv2.putText(image, f"ArUco {marker_id}", (center[0]-30, center[1]-10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    # Vẽ QR codes
    for i, qr in enumerate(result['qr_codes'], 1):
        polygon = np.array(qr['polygon'], dtype=np.int32)
        cv2.polylines(image, [polygon], True, (255, 0, 0), 3)
        
        # Vẽ label
        rect = qr['rect']
        cv2.putText(image, f"QR #{i}", (rect['left'], rect['top']-10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    
    # Hiển thị hoặc lưu
    if output_path:
        cv2.imwrite(output_path, image)
        print(f"✅ Đã lưu ảnh kết quả: {output_path}")
    else:
        cv2.imshow('Ballot Markers Detection', image)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Cách sử dụng:")
        print(f"  python {sys.argv[0]} <đường_dẫn_ảnh> [--visualize] [--output <file_output>]")
        print("\nVí dụ:")
        print(f"  python {sys.argv[0]} phieu_bau.jpg")
        print(f"  python {sys.argv[0]} phieu_bau.jpg --visualize")
        print(f"  python {sys.argv[0]} phieu_bau.jpg --visualize --output result.jpg")
        sys.exit(1)
    
    image_path = sys.argv[1]
    visualize = '--visualize' in sys.argv
    
    output_path = None
    if '--output' in sys.argv:
        output_idx = sys.argv.index('--output')
        if output_idx + 1 < len(sys.argv):
            output_path = sys.argv[output_idx + 1]
    
    # Đọc markers
    result = read_ballot_markers(image_path)
    
    # In thông tin
    print_marker_info(result)
    
    # Visualize nếu cần
    if visualize:
        visualize_markers(image_path, result, output_path)


if __name__ == "__main__":
    main()
