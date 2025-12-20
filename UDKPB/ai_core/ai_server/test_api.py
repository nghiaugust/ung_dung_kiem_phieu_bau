"""
Test script để demo API
"""
import requests
import os
import json
from pathlib import Path


def test_health_check(base_url):
    """Test health check endpoint"""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)
    
    url = f"{base_url}/api/health/"
    response = requests.get(url)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.status_code == 200


def test_model_info(base_url):
    """Test model info endpoint"""
    print("\n" + "="*60)
    print("TEST 2: Model Info")
    print("="*60)
    
    url = f"{base_url}/api/info/"
    response = requests.get(url)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.status_code == 200


def test_trocr_recognize(base_url, image_paths):
    """Test TrOCR recognize endpoint"""
    print("\n" + "="*60)
    print("TEST 3: TrOCR Recognize")
    print("="*60)
    
    url = f"{base_url}/api/trocr/recognize/"
    
    # Prepare files
    files = []
    for path in image_paths:
        if os.path.exists(path):
            files.append(('images', open(path, 'rb')))
            print(f"✓ Đã thêm: {os.path.basename(path)}")
        else:
            print(f"✗ Không tìm thấy: {path}")
    
    if not files:
        print("❌ Không có ảnh nào để test!")
        return False
    
    # Send request
    print(f"\nGửi {len(files)} ảnh đến API...")
    response = requests.post(url, files=files)
    
    # Close files
    for _, file in files:
        file.close()
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Success: {result['success']}")
        print(f"Count: {result['count']}")
        print("\nResults:")
        for r in result['results']:
            print(f"  - {r['filename']}: {r['text']} ({r['status']})")
    else:
        print(f"Error: {response.text}")
    
    return response.status_code == 200


def test_yolo_detect(base_url, image_paths):
    """Test YOLO detect endpoint"""
    print("\n" + "="*60)
    print("TEST 4: YOLO Detect")
    print("="*60)
    
    url = f"{base_url}/api/yolo/detect/"
    
    # Prepare files
    files = []
    for path in image_paths:
        if os.path.exists(path):
            files.append(('images', open(path, 'rb')))
            print(f"✓ Đã thêm: {os.path.basename(path)}")
        else:
            print(f"✗ Không tìm thấy: {path}")
    
    if not files:
        print("❌ Không có ảnh nào để test!")
        return False
    
    # Send request
    print(f"\nGửi {len(files)} ảnh đến API...")
    response = requests.post(url, files=files)
    
    # Close files
    for _, file in files:
        file.close()
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Success: {result['success']}")
        print(f"Count: {result['count']}")
        print("\nResults:")
        for r in result['results']:
            print(f"  - {r['filename']}: {r['label']} ({len(r['detections'])} detections, {r['status']})")
            for det in r['detections']:
                print(f"      • {det['class']}: {det['confidence']:.2f}")
    else:
        print(f"Error: {response.text}")
    
    return response.status_code == 200


def main():
    """Main test function"""
    # Base URL
    base_url = "http://localhost:8080"
    
    print("\n" + "="*60)
    print("🧪 AI SERVER API TEST SUITE")
    print("="*60)
    print(f"Base URL: {base_url}")
    
    # Test 1: Health check
    test1 = test_health_check(base_url)
    
    # Test 2: Model info
    test2 = test_model_info(base_url)
    
    # Tìm ảnh để test (có thể thay đổi đường dẫn này)
    # Ví dụ ảnh TrOCR (ảnh có chứa text tên người)
    trocr_images = []
    
    # Tìm trong thư mục ket_qua_tien_xu_ly_v2 nếu có
    test_dir = Path(__file__).parent.parent.parent / "ballot_processing_system" / "ket_qua_tien_xu_ly_v2"
    if test_dir.exists():
        trocr_images = [str(f) for f in test_dir.glob("*hoten*.jpg")][:3]  # Lấy 3 ảnh đầu
    
    # Test 3: TrOCR
    if trocr_images:
        test3 = test_trocr_recognize(base_url, trocr_images)
    else:
        print("\n⚠️ Không tìm thấy ảnh để test TrOCR. Bỏ qua test này.")
        print(f"   Hãy đặt ảnh trong thư mục: {test_dir}")
        test3 = None
    
    # Ví dụ ảnh YOLO (ảnh có chứa dấu X)
    yolo_images = []
    
    # Tìm ảnh trong thư mục ballot
    ballot_dir = Path(__file__).parent.parent.parent / "ballot_processing_system" / "ballot" / "data1"
    if ballot_dir.exists():
        yolo_images = [str(f) for f in ballot_dir.glob("*.jpg")][:2]  # Lấy 2 ảnh đầu
    
    # Test 4: YOLO
    if yolo_images:
        test4 = test_yolo_detect(base_url, yolo_images)
    else:
        print("\n⚠️ Không tìm thấy ảnh để test YOLO. Bỏ qua test này.")
        print(f"   Hãy đặt ảnh trong thư mục: {ballot_dir}")
        test4 = None
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    print(f"Test 1 (Health Check): {'✅ PASS' if test1 else '❌ FAIL'}")
    print(f"Test 2 (Model Info): {'✅ PASS' if test2 else '❌ FAIL'}")
    if test3 is not None:
        print(f"Test 3 (TrOCR): {'✅ PASS' if test3 else '❌ FAIL'}")
    else:
        print(f"Test 3 (TrOCR): ⏭️ SKIPPED")
    if test4 is not None:
        print(f"Test 4 (YOLO): {'✅ PASS' if test4 else '❌ FAIL'}")
    else:
        print(f"Test 4 (YOLO): ⏭️ SKIPPED")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Test bị gián đoạn bởi người dùng")
    except Exception as e:
        print(f"\n\n❌ Lỗi: {e}")
        import traceback
        traceback.print_exc()
