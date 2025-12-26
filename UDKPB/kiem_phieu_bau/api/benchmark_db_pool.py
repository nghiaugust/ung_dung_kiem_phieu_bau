"""
Benchmark để so sánh hiệu suất giữa connection pool và connection mặc định
Mô phỏng nhiều request đồng thời để thấy lợi ích của using('api_pool')
"""

import os
import sys
import django
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean, median, stdev

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kiem_phieu_bau.settings')
django.setup()

from django.db import connection, connections
from poll.models import Poll, PollMember
from django.contrib.auth import get_user_model

User = get_user_model()


class DatabaseBenchmark:
    """Benchmark class để test hiệu suất database connection"""
    
    def __init__(self, num_requests=100, num_threads=10):
        self.num_requests = num_requests
        self.num_threads = num_threads
        self.results_default = []
        self.results_pool = []
    
    def query_with_default_connection(self, iteration):
        """Query sử dụng connection mặc định"""
        start_time = time.time()
        
        try:
            # Thực hiện các query phức tạp
            polls = Poll.objects.all()[:10]
            
            for poll in polls:
                # Query thêm để tạo load
                members = PollMember.objects.filter(poll=poll, status='active')
                member_count = members.count()
                
                if member_count > 0:
                    users = User.objects.filter(
                        id__in=members.values_list('account_id', flat=True)
                    )
                    user_list = list(users)
            
            # Đóng connection để mô phỏng việc không có pool
            connection.close()
            
        except Exception as e:
            print(f"Error in default connection (iteration {iteration}): {e}")
            return None
        
        elapsed = time.time() - start_time
        return elapsed
    
    def query_with_pool_connection(self, iteration):
        """Query sử dụng connection pool (api_pool)"""
        start_time = time.time()
        
        try:
            # Thực hiện các query phức tạp với connection pool
            polls = Poll.objects.using('api_pool').all()[:10]
            
            for poll in polls:
                # Query thêm để tạo load
                members = PollMember.objects.using('api_pool').filter(poll=poll, status='active')
                member_count = members.count()
                
                if member_count > 0:
                    users = User.objects.using('api_pool').filter(
                        id__in=members.values_list('account_id', flat=True)
                    )
                    user_list = list(users)
            
            # Connection pool tự động quản lý, không cần close
            
        except Exception as e:
            print(f"Error in pool connection (iteration {iteration}): {e}")
            return None
        
        elapsed = time.time() - start_time
        return elapsed
    
    def run_benchmark_default(self):
        """Chạy benchmark với connection mặc định"""
        print(f"\n{'='*60}")
        print(f"Running benchmark: DEFAULT CONNECTION")
        print(f"Requests: {self.num_requests}, Threads: {self.num_threads}")
        print(f"{'='*60}\n")
        
        start_total = time.time()
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [
                executor.submit(self.query_with_default_connection, i)
                for i in range(self.num_requests)
            ]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    self.results_default.append(result)
                    print(f"Request completed in {result:.4f}s")
        
        total_time = time.time() - start_total
        
        print(f"\n{'='*60}")
        print(f"DEFAULT CONNECTION - Summary")
        print(f"{'='*60}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Successful requests: {len(self.results_default)}/{self.num_requests}")
        
        if self.results_default:
            print(f"Average response time: {mean(self.results_default):.4f}s")
            print(f"Median response time: {median(self.results_default):.4f}s")
            print(f"Min response time: {min(self.results_default):.4f}s")
            print(f"Max response time: {max(self.results_default):.4f}s")
            if len(self.results_default) > 1:
                print(f"Std deviation: {stdev(self.results_default):.4f}s")
            print(f"Requests per second: {len(self.results_default)/total_time:.2f}")
        print(f"{'='*60}\n")
    
    def run_benchmark_pool(self):
        """Chạy benchmark với connection pool"""
        print(f"\n{'='*60}")
        print(f"Running benchmark: CONNECTION POOL (api_pool)")
        print(f"Requests: {self.num_requests}, Threads: {self.num_threads}")
        print(f"{'='*60}\n")
        
        start_total = time.time()
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [
                executor.submit(self.query_with_pool_connection, i)
                for i in range(self.num_requests)
            ]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    self.results_pool.append(result)
                    print(f"Request completed in {result:.4f}s")
        
        total_time = time.time() - start_total
        
        print(f"\n{'='*60}")
        print(f"CONNECTION POOL - Summary")
        print(f"{'='*60}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Successful requests: {len(self.results_pool)}/{self.num_requests}")
        
        if self.results_pool:
            print(f"Average response time: {mean(self.results_pool):.4f}s")
            print(f"Median response time: {median(self.results_pool):.4f}s")
            print(f"Min response time: {min(self.results_pool):.4f}s")
            print(f"Max response time: {max(self.results_pool):.4f}s")
            if len(self.results_pool) > 1:
                print(f"Std deviation: {stdev(self.results_pool):.4f}s")
            print(f"Requests per second: {len(self.results_pool)/total_time:.2f}")
        print(f"{'='*60}\n")
    
    def compare_results(self):
        """So sánh kết quả giữa 2 phương pháp"""
        print(f"\n{'='*60}")
        print(f"COMPARISON RESULTS")
        print(f"{'='*60}\n")
        
        if not self.results_default or not self.results_pool:
            print("Không đủ dữ liệu để so sánh")
            return
        
        avg_default = mean(self.results_default)
        avg_pool = mean(self.results_pool)
        improvement = ((avg_default - avg_pool) / avg_default) * 100
        
        print(f"Average Response Time:")
        print(f"  Default Connection: {avg_default:.4f}s")
        print(f"  Connection Pool:    {avg_pool:.4f}s")
        print(f"  Improvement:        {improvement:.2f}%")
        print(f"  Faster by:          {avg_default - avg_pool:.4f}s\n")
        
        median_default = median(self.results_default)
        median_pool = median(self.results_pool)
        
        print(f"Median Response Time:")
        print(f"  Default Connection: {median_default:.4f}s")
        print(f"  Connection Pool:    {median_pool:.4f}s\n")
        
        if avg_pool < avg_default:
            print(f"✓ Connection Pool is FASTER by {improvement:.2f}%")
        else:
            print(f"✗ Connection Pool is SLOWER")
        
        print(f"\n{'='*60}\n")


def main():
    """Main function để chạy benchmark"""
    print("\n" + "="*60)
    print("DATABASE CONNECTION POOL BENCHMARK")
    print("="*60)
    print("\nĐây là benchmark để so sánh hiệu suất giữa:")
    print("1. Connection mặc định (đóng mở connection mỗi request)")
    print("2. Connection Pool (sử dụng 'api_pool' - tái sử dụng connection)")
    print("\nKhi có nhiều request đồng thời, connection pool sẽ:")
    print("- Giảm overhead của việc tạo/đóng connection")
    print("- Tái sử dụng connection đã có")
    print("- Tăng throughput và giảm latency")
    print("="*60)
    
    # Cấu hình benchmark
    NUM_REQUESTS = 50  # Số lượng request để test
    NUM_THREADS = 10   # Số thread đồng thời
    
    print(f"\nConfiguration:")
    print(f"  Total requests: {NUM_REQUESTS}")
    print(f"  Concurrent threads: {NUM_THREADS}")
    print(f"  Database: {connections['default'].settings_dict['NAME']}")
    
    input("\nPress ENTER to start benchmark...")
    
    # Tạo benchmark instance
    benchmark = DatabaseBenchmark(
        num_requests=NUM_REQUESTS,
        num_threads=NUM_THREADS
    )
    
    # Chạy benchmark với connection mặc định
    benchmark.run_benchmark_default()
    
    # Đợi một chút trước khi chạy test tiếp theo
    print("\nWaiting 3 seconds before next test...")
    time.sleep(3)
    
    # Chạy benchmark với connection pool
    benchmark.run_benchmark_pool()
    
    # So sánh kết quả
    benchmark.compare_results()
    
    # Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    print("\nĐể tối ưu hóa hiệu suất API:")
    print("1. Sử dụng using('api_pool') cho tất cả query trong API views")
    print("2. Cấu hình CONN_MAX_AGE trong settings.py cho api_pool")
    print("3. Tăng CONN_MAX_AGE nếu có nhiều request liên tục")
    print("4. Monitor số lượng connection đang mở")
    print("5. Điều chỉnh max_connections của PostgreSQL/MySQL nếu cần")
    print("\nVí dụ trong settings.py:")
    print("  DATABASES = {")
    print("      'api_pool': {")
    print("          'ENGINE': 'django.db.backends.postgresql',")
    print("          'CONN_MAX_AGE': 600,  # Keep connection 10 minutes")
    print("          'OPTIONS': {")
    print("              'connect_timeout': 10,")
    print("          }")
    print("      }")
    print("  }")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
