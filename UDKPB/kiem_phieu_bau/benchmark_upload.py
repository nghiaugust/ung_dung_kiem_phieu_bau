"""
Benchmark Script: So sánh hiệu suất upload giữa runserver và Waitress
Chạy script này khi server đang chạy để test performance
"""
import requests
import time
import os
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import statistics

# ==================== CẤU HÌNH ====================
BASE_URL = "http://192.168.56.1:8000"  # Thay đổi nếu cần
API_ENDPOINT = f"{BASE_URL}/api/test-upload/"  # API endpoint đơn giản cho benchmark

# Token/Authentication (KHÔNG CẦN cho test-upload endpoint)
HEADERS = {}

# File sizes để test (bytes)
TEST_FILE_SIZES = [
    (1 * 1024 * 1024, "1MB"),   # 1MB
]

# Số lượng concurrent users để test
CONCURRENT_USERS = [1, 3, 8, 15]

# Số file mỗi user upload liên tiếp
FILES_PER_USER = 30

# ==================== HELPER FUNCTIONS ====================

def create_test_file(size_bytes):
    """Tạo file test với kích thước chỉ định (giả lập ảnh JPG)"""
    # Tạo file giả với header JPG để giống file thật hơn
    jpg_header = b'\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    remaining_bytes = size_bytes - len(jpg_header) - 2  # -2 cho footer
    jpg_footer = b'\xFF\xD9'
    
    if remaining_bytes < 0:
        remaining_bytes = 0
    
    file_content = jpg_header + (b'X' * remaining_bytes) + jpg_footer
    return io.BytesIO(file_content)

def upload_file(file_data, file_size_name, user_id):
    """Upload một file và trả về thời gian xử lý (Legacy - không dùng nữa)"""
    file_data.seek(0)  # Reset file pointer
    
    files = {
        'file': (f'test_{file_size_name}_{user_id}.jpg', file_data, 'image/jpeg')
    }
    
    start_time = time.time()
    
    try:
        response = requests.post(
            API_ENDPOINT,
            files=files,
            headers=HEADERS,
            timeout=180
        )
        
        elapsed_time = time.time() - start_time
        
        return {
            'success': response.status_code == 200,
            'status_code': response.status_code,
            'elapsed_time': elapsed_time,
            'user_id': user_id
        }
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'status_code': 'TIMEOUT',
            'elapsed_time': time.time() - start_time,
            'user_id': user_id
        }
    except Exception as e:
        return {
            'success': False,
            'status_code': f'ERROR: {str(e)}',
            'elapsed_time': time.time() - start_time,
            'user_id': user_id
        }

def upload_multiple_files_batch(file_size_bytes, file_size_name, user_id, num_files):
    """Một user upload nhiều files trong 1 request (batch upload)"""
    
    # Tạo danh sách files để upload cùng lúc
    files_list = []
    for file_num in range(1, num_files + 1):
        file_data = create_test_file(file_size_bytes)
        file_data.seek(0)
        filename = f'test_{file_size_name}_user{user_id}_file{file_num}.jpg'
        files_list.append(('file', (filename, file_data, 'image/jpeg')))
    
    start_time = time.time()
    
    try:
        # Upload tất cả files trong 1 request
        response = requests.post(
            API_ENDPOINT,
            files=files_list,
            headers=HEADERS,
            timeout=300  # Tăng timeout vì upload nhiều files
        )
        
        elapsed_time = time.time() - start_time
        
        # Parse response
        if response.status_code == 200:
            data = response.json()
            uploaded_count = data.get('total_files', 0)
        else:
            uploaded_count = 0
        
        return {
            'success': response.status_code == 200,
            'status_code': response.status_code,
            'elapsed_time': elapsed_time,
            'user_id': user_id,
            'files_uploaded': uploaded_count,
            'expected_files': num_files
        }
        
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'status_code': 'TIMEOUT',
            'elapsed_time': time.time() - start_time,
            'user_id': user_id,
            'files_uploaded': 0,
            'expected_files': num_files
        }
    except Exception as e:
        return {
            'success': False,
            'status_code': f'ERROR: {str(e)}',
            'elapsed_time': time.time() - start_time,
            'user_id': user_id,
            'files_uploaded': 0,
            'expected_files': num_files
        }

def test_concurrent_uploads(file_size_bytes, file_size_name, num_users):
    """Test upload với số lượng users đồng thời, mỗi user upload nhiều files trong 1 request"""
    print(f"\n📤 Testing {file_size_name} with {num_users} concurrent users...")
    print(f"   Each user uploads {FILES_PER_USER} files in 1 batch request")
    
    results = []
    start_time = time.time()
    
    # Mỗi user sẽ upload FILES_PER_USER files trong 1 request
    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = [
            executor.submit(upload_multiple_files_batch, file_size_bytes, file_size_name, i+1, FILES_PER_USER)
            for i in range(num_users)
        ]
        
        for future in as_completed(futures):
            # Mỗi future trả về kết quả từ 1 user
            result = future.result()
            results.append(result)
    
    total_time = time.time() - start_time
    
    # Phân tích kết quả
    success_requests = sum(1 for r in results if r['success'])
    failed_requests = num_users - success_requests
    
    total_files_uploaded = sum(r['files_uploaded'] for r in results)
    total_expected_files = num_users * FILES_PER_USER
    
    if success_requests > 0:
        success_times = [r['elapsed_time'] for r in results if r['success']]
        avg_time = statistics.mean(success_times)
        min_time = min(success_times)
        max_time = max(success_times)
    else:
        avg_time = min_time = max_time = 0
    
    return {
        'file_size': file_size_name,
        'num_users': num_users,
        'files_per_user': FILES_PER_USER,
        'total_requests': num_users,
        'success_requests': success_requests,
        'failed_requests': failed_requests,
        'total_files_uploaded': total_files_uploaded,
        'total_expected_files': total_expected_files,
        'total_time': total_time,
        'avg_time': avg_time,
        'min_time': min_time,
        'max_time': max_time,
        'throughput_requests': success_requests / total_time if total_time > 0 else 0,
        'throughput_files': total_files_uploaded / total_time if total_time > 0 else 0
    }

def print_results(results, output_file=None):
    """In kết quả benchmark và lưu ra file txt"""
    output_lines = []
    
    def output(text):
        """In ra console và lưu vào list"""
        print(text)
        output_lines.append(text)
    
    output("\n" + "=" * 80)
    output("📊 BENCHMARK RESULTS")
    output("=" * 80)
    
    for result in results:
        output(f"\n📦 File Size: {result['file_size']} | 👥 Users: {result['num_users']} | 📁 Files/User: {result['files_per_user']}")
        output(f"   📊 Total Requests: {result['total_requests']} batch requests")
        output(f"   ✅ Success Requests: {result['success_requests']}/{result['total_requests']}")
        output(f"   ❌ Failed Requests:  {result['failed_requests']}")
        output(f"   📁 Total Files: {result['total_files_uploaded']}/{result['total_expected_files']} uploaded")
        output(f"   ⏱️  Total Time: {result['total_time']:.2f}s")
        
        if result['success_requests'] > 0:
            output(f"   📈 Avg Time/Request: {result['avg_time']:.2f}s (to upload {result['files_per_user']} files)")
            output(f"   ⚡ Min Time: {result['min_time']:.2f}s")
            output(f"   🐌 Max Time: {result['max_time']:.2f}s")
            output(f"   🚀 Throughput: {result['throughput_requests']:.2f} batch-requests/sec")
            output(f"   📂 File Throughput: {result['throughput_files']:.2f} files/sec")
            
            # Data throughput
            total_mb = (result['total_files_uploaded'] * 1)  # 1MB per file
            mb_per_sec = total_mb / result['total_time'] if result['total_time'] > 0 else 0
            output(f"   💾 Data Throughput: {mb_per_sec:.2f} MB/sec")
    
    # Lưu ra file nếu có output_file
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        print(f"\n✅ Results saved to: {output_file}")

def check_server():
    """Kiểm tra server có đang chạy không"""
    try:
        response = requests.get(BASE_URL, timeout=5)
        return True
    except:
        return False

def cleanup_benchmark_files():
    """Xóa tất cả files test trong thư mục media/benchmark_test"""
    try:
        import shutil
        
        # Đường dẫn tới thư mục benchmark_test
        benchmark_dir = os.path.join(os.path.dirname(__file__), 'media', 'benchmark_test')
        
        if os.path.exists(benchmark_dir):
            # Đếm số files trước khi xóa
            file_count = len([f for f in os.listdir(benchmark_dir) if os.path.isfile(os.path.join(benchmark_dir, f))])
            
            # Xóa toàn bộ thư mục và tạo lại
            shutil.rmtree(benchmark_dir)
            os.makedirs(benchmark_dir, exist_ok=True)
            
            print(f"\n🗑️  Cleaned up {file_count} test files from media/benchmark_test/")
        else:
            print("\n✅ No cleanup needed - benchmark directory doesn't exist")
    except Exception as e:
        print(f"\n⚠️  Cleanup warning: {e}")

# ==================== MAIN BENCHMARK ====================

def run_benchmark():
    print("=" * 80)
    print("🔥 UPLOAD PERFORMANCE BENCHMARK")
    print("=" * 80)
    print(f"🌐 Server: {BASE_URL}")
    print(f"📍 API Endpoint: {API_ENDPOINT}")
    print()
    
    # Kiểm tra server
    print("🔍 Checking server status...")
    if not check_server():
        print(f"❌ ERROR: Server is not running at {BASE_URL}")
        print("⚠️  Please start the server first:")
        print("   - For runserver: python manage.py runserver")
        print("   - For Waitress:  python run_waitress.py")
        return
    
    print("✅ Server is running!\n")
    
    # Chạy benchmark
    all_results = []
    
    for file_size_bytes, file_size_name in TEST_FILE_SIZES:
        for num_users in CONCURRENT_USERS:
            result = test_concurrent_uploads(file_size_bytes, file_size_name, num_users)
            all_results.append(result)
            
            # Delay nhỏ giữa các test
            time.sleep(1)
    
    # Tạo tên file output với timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"benchmark_results_{timestamp}.txt"
    
    # In kết quả và lưu ra file
    print_results(all_results, output_filename)
    
    # So sánh tóm tắt
    print("\n" + "=" * 80)
    print("💡 PERFORMANCE ANALYSIS")
    print("=" * 80)
    
    # Tìm test case khó nhất (15 users, 50 files mỗi user)
    hard_test = [r for r in all_results if r['num_users'] == 15]
    if hard_test:
        result = hard_test[0]
        if result['total_files_uploaded'] == result['total_expected_files']:
            print(f"✅ EXCELLENT: Server handled {result['num_users']} concurrent batch uploads!")
            print(f"   Each user uploaded {result['files_per_user']} files in 1 request")
            print(f"   Total: {result['total_files_uploaded']} files in {result['total_time']:.2f}s")
            print(f"   Average time per batch: {result['avg_time']:.2f}s")
            print(f"   File throughput: {result['throughput_files']:.2f} files/sec")
            
            total_mb = result['total_files_uploaded'] * 1
            mb_per_sec = total_mb / result['total_time'] if result['total_time'] > 0 else 0
            print(f"   Data throughput: {mb_per_sec:.2f} MB/sec")
        else:
            print(f"⚠️  WARNING: Server struggled with {result['num_users']} concurrent batch uploads")
            print(f"   Only {result['total_files_uploaded']}/{result['total_expected_files']} files uploaded")
    
    print("\n💡 Test Configuration:")
    print(f"   - File size: 1MB per file")
    print(f"   - Files per user: {FILES_PER_USER} files")
    print(f"   - Upload mode: Batch upload (all files in 1 request)")
    print(f"   - Concurrent users: {CONCURRENT_USERS}")
    print(f"   - Total data per user: {FILES_PER_USER}MB")
    print("\n💡 Recommendations:")
    print("   - Chạy benchmark với runserver: python manage.py runserver")
    print("   - Chạy lại với Waitress: python run_waitress.py")
    print("   - So sánh kết quả để thấy sự khác biệt!")
    print("=" * 80)
    
    # Cleanup files sau khi test xong
    cleanup_benchmark_files()

if __name__ == '__main__':
    print("\n" + "=" * 80)
    print("⚠️  SETUP INSTRUCTIONS")
    print("=" * 80)
    print("1. ✅ API Endpoint đã cấu hình: /api/test-upload/")
    print("2. ✅ Không cần authentication token")
    print("3. 📊 Test Configuration:")
    print(f"   - File size: 1MB per file")
    print(f"   - Files per user: {FILES_PER_USER} files")
    print(f"   - Upload mode: BATCH (all files in 1 request)")
    print(f"   - Concurrent users: {CONCURRENT_USERS}")
    print(f"   - Total test cases: {len(CONCURRENT_USERS)}")
    print("\n💡 Mô phỏng: Người dùng chọn nhiều file và upload cùng lúc")
    print("4. ⚙️  Đảm bảo server đang chạy:")
    print("   - Với runserver: python manage.py runserver")
    print("   - Với Waitress:  python run_waitress.py")
    print("=" * 80)
    print()
    
    input("Press ENTER to start benchmark...")
    
    try:
        run_benchmark()
    except KeyboardInterrupt:
        print("\n\n⏹️  Benchmark interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
