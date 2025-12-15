"""
Module đọc QR code và ArUco markers từ ảnh phiếu bầu
"""
import cv2
import numpy as np
import json
import sys
from pyzbar import pyzbar


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
    
    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            corner = corners[i][0]
            # Tính tọa độ trung tâm
            center_x = int(np.mean(corner[:, 0]))
            center_y = int(np.mean(corner[:, 1]))
            
            # Tính kích thước marker
            width = int(np.linalg.norm(corner[1] - corner[0]))
            height = int(np.linalg.norm(corner[2] - corner[1]))
            
            markers_info[int(marker_id)] = {
                'id': int(marker_id),
                'center': (center_x, center_y),
                'corners': corner.tolist(),
                'size': (width, height)
            }
    
    return markers_info


def detect_qr_codes(image):
    """
    Detect QR codes trong ảnh với xử lý thông minh (tự động thử nhiều kỹ thuật)
    
    Args:
        image: Ảnh đầu vào (numpy array)
    
    Returns:
        list: Danh sách thông tin QR codes tìm thấy
    """
    qr_codes = []
    found_data = set()  # Tránh trùng lặp
    
    # Thử decode trực tiếp trước
    decoded_objects = pyzbar.decode(image)
    
    for obj in decoded_objects:
        data = obj.data.decode('utf-8')
        if data not in found_data:
            found_data.add(data)
            qr_codes.append(_create_qr_info(obj, data))
    
    if qr_codes:
        return qr_codes
    
    # Step 2: Thử với ảnh được upscale 2x
    if not qr_codes:
        upscaled_2x = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        decoded_objects = pyzbar.decode(upscaled_2x)
        for obj in decoded_objects:
            data = obj.data.decode('utf-8')
            if data not in found_data:
                found_data.add(data)
                # Điều chỉnh tọa độ về kích thước gốc
                qr_info = _create_qr_info(obj, data)
                qr_info['rect'] = {k: v // 2 for k, v in qr_info['rect'].items()}
                qr_info['polygon'] = [(x // 2, y // 2) for x, y in qr_info['polygon']]
                qr_codes.append(qr_info)
        
        if qr_codes:
            return qr_codes
        
        # Step 3: Thử với ảnh được upscale 3x
        if not qr_codes:
            upscaled_3x = cv2.resize(image, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
            decoded_objects = pyzbar.decode(upscaled_3x)
            for obj in decoded_objects:
                data = obj.data.decode('utf-8')
                if data not in found_data:
                    found_data.add(data)
                    # Điều chỉnh tọa độ về kích thước gốc
                    qr_info = _create_qr_info(obj, data)
                    qr_info['rect'] = {k: v // 3 for k, v in qr_info['rect'].items()}
                    qr_info['polygon'] = [(x // 3, y // 3) for x, y in qr_info['polygon']]
                    qr_codes.append(qr_info)
        
        if qr_codes:
            return qr_codes
        
        # Step 4: Thử kết hợp sharpen + upscale 3x
        if not qr_codes:
            # Sharpen trước
            kernel_sharpen = np.array([[-1,-1,-1],
                                       [-1, 9,-1],
                                       [-1,-1,-1]])
            sharpened = cv2.filter2D(image, -1, kernel_sharpen)
            # Sau đó upscale 3x
            upscaled_sharp_3x = cv2.resize(sharpened, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
            decoded_objects = pyzbar.decode(upscaled_sharp_3x)
            for obj in decoded_objects:
                data = obj.data.decode('utf-8')
                if data not in found_data:
                    found_data.add(data)
                    # Điều chỉnh tọa độ về kích thước gốc
                    qr_info = _create_qr_info(obj, data)
                    qr_info['rect'] = {k: v // 3 for k, v in qr_info['rect'].items()}
                    qr_info['polygon'] = [(x // 3, y // 3) for x, y in qr_info['polygon']]
                    qr_codes.append(qr_info)
def _create_qr_info(obj, data):
    """
    Tạo dictionary thông tin QR code từ decoded object
    
    Args:
        obj: Decoded object từ pyzbar
        data: Dữ liệu đã decode (string)
    
    Returns:
        dict: Thông tin QR code
    """
    rect = obj.rect
    polygon = obj.polygon
    
    qr_info = {
        'type': obj.type,
        'data': data,
        'rect': {
            'left': rect.left,
            'top': rect.top,
            'width': rect.width,
            'height': rect.height
        },
        'polygon': [(p.x, p.y) for p in polygon]
    }
    
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
