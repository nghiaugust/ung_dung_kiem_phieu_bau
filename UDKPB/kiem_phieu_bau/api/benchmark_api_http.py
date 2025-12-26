"""
Benchmark HTTP API để so sánh hiệu suất giữa API có connection pool và không có pool
Gọi thực tế các API endpoints qua HTTP requests
"""

import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean, median


class APIBenchmark:
    """Benchmark class để test hiệu suất API qua HTTP"""
    
    def __init__(self, base_url, token, num_requests=100, num_threads=10):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.num_requests = num_requests
        self.num_threads = num_threads
        self.results_with_pool = []
        self.results_without_pool = []
        self.wall_clock_with_pool = 0
        self.wall_clock_without_pool = 0
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def call_api_with_pool(self, iteration):
        """Gọi API endpoint có sử dụng connection pool"""
        start_time = time.time()
        
        try:
            response = requests.get(
                f'{self.base_url}/polls/',
                headers=self.headers,
                params={'limit': 20, 'offset': 0},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                elapsed = time.time() - start_time
                return elapsed
            else:
                return None
                
        except Exception as e:
            return None
    
    def call_api_without_pool(self, iteration):
        """Gọi API endpoint không sử dụng connection pool"""
        start_time = time.time()
        
        try:
            response = requests.get(
                f'{self.base_url}/polls-no-pool/',
                headers=self.headers,
                params={'limit': 20, 'offset': 0},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                elapsed = time.time() - start_time
                return elapsed
            else:
                return None
                
        except Exception as e:
            return None
    
    def run_benchmark_with_pool(self):
        """Chạy benchmark với API có connection pool"""
        print(f"\n[1/2] Kiểm tra CÓ connection pool ({self.num_requests} requests, {self.num_threads} threads)...")
        
        start_total = time.time()
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [
                executor.submit(self.call_api_with_pool, i)
                for i in range(self.num_requests)
            ]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    self.results_with_pool.append(result)
        
        total_time = time.time() - start_total
        self.wall_clock_with_pool = total_time
        
        print(f"✓ Hoàn thành: {len(self.results_with_pool)}/{self.num_requests} requests trong {total_time:.2f}s")
    
    def run_benchmark_without_pool(self):
        """Chạy benchmark với API không có connection pool"""
        print(f"\n[2/2] Kiểm tra KHÔNG connection pool ({self.num_requests} requests, {self.num_threads} threads)...")
        
        start_total = time.time()
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [
                executor.submit(self.call_api_without_pool, i)
                for i in range(self.num_requests)
            ]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    self.results_without_pool.append(result)
        
        total_time = time.time() - start_total
        self.wall_clock_without_pool = total_time
        
        print(f"✓ Hoàn thành: {len(self.results_without_pool)}/{self.num_requests} requests trong {total_time:.2f}s")
    
    def compare_results(self):
        """So sánh kết quả giữa 2 phương pháp"""
        print(f"\n{'='*70}")
        print(f"KẾT QUẢ BENCHMARK (Mô phỏng DB từ xa với 50ms overhead kết nối)")
        print(f"{'='*70}\n")
        
        if not self.results_with_pool or not self.results_without_pool:
            print("❌ Không đủ dữ liệu để so sánh")
            return
        
        # Metrics
        wall_with = self.wall_clock_with_pool
        wall_without = self.wall_clock_without_pool
        wall_improvement = ((wall_without - wall_with) / wall_without) * 100 if wall_without > 0 else 0
        
        avg_with = mean(self.results_with_pool)
        avg_without = mean(self.results_without_pool)
        avg_improvement = ((avg_without - avg_with) / avg_without) * 100
        
        rps_with = len(self.results_with_pool) / wall_with if wall_with > 0 else 0
        rps_without = len(self.results_without_pool) / wall_without if wall_without > 0 else 0
        
        # Display results
        print(f"{'Chỉ số':<30} {'CÓ Pool':>15} {'KHÔNG Pool':>15} {'Cải thiện':>15}")
        print(f"{'-'*30} {'-'*15} {'-'*15} {'-'*15}")
        print(f"{'Thời gian thực tế (s)':<30} {wall_with:>15.2f} {wall_without:>15.2f} {wall_improvement:>14.1f}%")
        print(f"{'Lượng xử lý (req/s)':<30} {rps_with:>15.2f} {rps_without:>15.2f} {((rps_with-rps_without)/rps_without*100):>14.1f}%")
        print(f"{'TG phản hồi TB (s)':<30} {avg_with:>15.4f} {avg_without:>15.4f} {avg_improvement:>14.1f}%")
        print(f"{'TG phản hồi giữa (s)':<30} {median(self.results_with_pool):>15.4f} {median(self.results_without_pool):>15.4f} {'':>15}")
        print(f"{'TG phản hồi min (s)':<30} {min(self.results_with_pool):>15.4f} {min(self.results_without_pool):>15.4f} {'':>15}")
        print(f"{'TG phản hồi max (s)':<30} {max(self.results_with_pool):>15.4f} {max(self.results_without_pool):>15.4f} {'':>15}")
        
        print(f"\n{'='*70}")
        print(f"KẾT LUẬN:")
        print(f"{'='*70}")
        if wall_with < wall_without:
            print(f"✅ Connection Pool NHANH HƠN {wall_improvement:.1f}%")
            print(f"   - Tiết kiệm {wall_without - wall_with:.2f}s tổng thời gian")
            print(f"   - Xử lý thêm {rps_with - rps_without:.2f} requests/giây")
            print(f"   - Mỗi request nhanh hơn {(avg_without - avg_with)*1000:.1f}ms trung bình")
        else:
            print(f"❌ Connection Pool CHẬM HƠN {abs(wall_improvement):.1f}%")
        print(f"{'='*70}\n")


def test_connection():
    """Kiểm tra kết nối đến API server"""
    base_url = "http://192.168.56.1:8000/api"
    
    print("Kiểm tra kết nối...", end=" ")
    
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        print(f"✓ Kết nối thành công")
        return True
    except requests.exceptions.RequestException as e:
        print(f"✗ Thất bại\nLỗi: {e}")
        return False


def get_auth_token():
    """Đăng nhập và lấy token"""
    base_url = "http://192.168.56.1:8000/api"
    
    username = input("Username [admin]: ").strip() or "admin"
    password = input("Password [admin]: ").strip() or "admin"
    
    print("Đang xác thực...", end=" ")
    try:
        response = requests.post(
            f'{base_url}/login/',
            json={'username': username, 'password': password},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                token = data.get('token')
                print(f"✓ Đăng nhập thành công với tài khoản {username}")
                return token
        
        print(f"✗ Thất bại")
        return None
            
    except Exception as e:
        print(f"✗ Lỗi: {e}")
        return None


def main():
    """Main function để chạy benchmark"""
    print("\n" + "="*70)
    print("BENCHMARK CONNECTION POOL CHO API")
    print("Mô phỏng database từ xa với 50ms độ trễ kết nối")
    print("="*70 + "\n")
    
    BASE_URL = "http://192.168.56.1:8000/api"
    NUM_REQUESTS = 100
    NUM_THREADS = 10
    
    if not test_connection():
        return
    
    token = get_auth_token()
    if not token:
        print("❌ Xác thực thất bại")
        return
    
    print(f"\nCấu hình: {NUM_REQUESTS} requests, {NUM_THREADS} threads")
    input("Nhấn ENTER để bắt đầu...\n")
    
    benchmark = APIBenchmark(BASE_URL, token, NUM_REQUESTS, NUM_THREADS)
    
    benchmark.run_benchmark_with_pool()
    time.sleep(2)
    benchmark.run_benchmark_without_pool()
    benchmark.compare_results()


if __name__ == '__main__':
    main()
