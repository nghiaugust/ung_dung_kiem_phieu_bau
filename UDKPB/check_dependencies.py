"""
Script kiểm tra dependencies của dự án UDKPB
- Quét tất cả file Python để tìm imports
- So sánh với requirements.txt
- Báo cáo thư viện thiếu hoặc thừa
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# Mapping từ import name sang package name (vì nhiều khi khác nhau)
IMPORT_TO_PACKAGE = {
    'cv2': 'opencv-python',
    'PIL': 'Pillow',
    'dotenv': 'python-dotenv',
    'MySQLdb': 'mysqlclient',
    'jwt': 'PyJWT',
    'skimage': 'scikit-image',
    'sklearn': 'scikit-learn',
    'yaml': 'PyYAML',
    'bs4': 'beautifulsoup4',
    'rest_framework': 'djangorestframework',
    'channels': 'channels',
    'celery': 'celery',
    'redis': 'redis',
    'waitress': 'waitress',
    'gevent': 'gevent',
    'eventlet': 'eventlet',
    'flower': 'flower',
    'streamlit': 'streamlit',
}

# Thư viện built-in của Python (không cần cài)
BUILTIN_MODULES = {
    'os', 'sys', 'json', 'time', 'datetime', 're', 'math', 'random',
    'collections', 'itertools', 'functools', 'operator', 'pathlib',
    'typing', 'abc', 'io', 'logging', 'unittest', 'argparse', 'subprocess',
    'threading', 'multiprocessing', 'queue', 'socket', 'http', 'urllib',
    'email', 'base64', 'hashlib', 'hmac', 'secrets', 'uuid', 'warnings',
    'traceback', 'inspect', 'copy', 'pickle', 'csv', 'xml', 'html',
    'sqlite3', 'configparser', 'tempfile', 'shutil', 'glob', 'fnmatch',
    'platform', 'ctypes', 'struct', 'array', 'heapq', 'bisect', 'weakref',
    'enum', 'dataclasses', 'contextlib', 'atexit', 'signal', 'asyncio',
}


def find_imports_in_file(filepath):
    """Tìm tất cả imports trong một file Python"""
    imports = set()
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        # Pattern 1: import xxx
        pattern1 = r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        # Pattern 2: from xxx import yyy
        pattern2 = r'^from\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        
        for match in re.finditer(pattern1, content, re.MULTILINE):
            module = match.group(1)
            imports.add(module)
            
        for match in re.finditer(pattern2, content, re.MULTILINE):
            module = match.group(1)
            imports.add(module)
            
    except Exception as e:
        print(f"⚠️  Lỗi đọc file {filepath}: {e}")
    
    return imports


def scan_project(root_dir):
    """Quét toàn bộ dự án tìm imports"""
    all_imports = defaultdict(list)
    
    # Chỉ quét trong thư mục kiem_phieu_bau và ai_core
    scan_dirs = [
        os.path.join(root_dir, 'kiem_phieu_bau'),
        os.path.join(root_dir, 'ai_core'),
    ]
    
    for scan_dir in scan_dirs:
        if not os.path.exists(scan_dir):
            continue
            
        for root, dirs, files in os.walk(scan_dir):
            # Bỏ qua các thư mục không cần
            dirs[:] = [d for d in dirs if d not in {
                '__pycache__', 'migrations', 'venv', 'env', 
                '.git', 'static', 'media', 'staticfiles',
                'model_vietnameocr',
            }]
            
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    imports = find_imports_in_file(filepath)
                    
                    for imp in imports:
                        all_imports[imp].append(filepath)
    
    return all_imports


def read_requirements(req_file):
    """Đọc file requirements.txt"""
    requirements = set()
    
    if not os.path.exists(req_file):
        return requirements
    
    try:
        with open(req_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Lấy tên package (bỏ version)
                    pkg = re.split(r'[=><~!]', line)[0].strip()
                    requirements.add(pkg.lower())
    except Exception as e:
        print(f"⚠️  Lỗi đọc {req_file}: {e}")
    
    return requirements


def main():
    print("=" * 80)
    print("🔍 KIỂM TRA DEPENDENCIES CỦA DỰ ÁN UDKPB")
    print("=" * 80)
    print()
    
    # Xác định thư mục gốc
    script_dir = Path(__file__).parent
    project_root = script_dir
    
    # Đọc requirements.txt
    req_files = [
        os.path.join(project_root, 'requirements.txt'),
        os.path.join(project_root, 'kiem_phieu_bau', 'celery_requirements.txt'),
        os.path.join(project_root, 'ai_core', 'ai_server', 'requirements.txt'),
    ]
    
    all_requirements = set()
    for req_file in req_files:
        if os.path.exists(req_file):
            reqs = read_requirements(req_file)
            all_requirements.update(reqs)
            print(f"📄 Đọc {os.path.basename(req_file)}: {len(reqs)} packages")
    
    print(f"\n✅ Tổng số packages trong requirements: {len(all_requirements)}")
    print()
    
    # Quét imports trong code
    print("🔎 Đang quét imports trong code...")
    all_imports = scan_project(project_root)
    
    # Lọc ra các imports là third-party (không phải built-in, không phải local)
    third_party_imports = {}
    for module, files in all_imports.items():
        # Bỏ qua built-in modules
        if module in BUILTIN_MODULES:
            continue
        
        # Bỏ qua local apps của Django
        if module in {'account', 'poll', 'ballot', 'api', 'counting', 
                      'form', 'preprocessing', 'quan_ly_phieu_bau', 
                      'security', 'websocket', 'kiem_phieu_bau'}:
            continue
        
        third_party_imports[module] = files
    
    print(f"✅ Tìm thấy {len(third_party_imports)} third-party imports\n")
    
    # Mapping imports sang package names
    required_packages = set()
    for module in third_party_imports.keys():
        package = IMPORT_TO_PACKAGE.get(module, module.lower())
        required_packages.add(package)
    
    # So sánh
    print("=" * 80)
    print("📊 KẾT QUẢ PHÂN TÍCH")
    print("=" * 80)
    print()
    
    # 1. Packages được import nhưng THIẾU trong requirements
    missing = required_packages - all_requirements
    if missing:
        print("❌ THIẾU trong requirements.txt:")
        print("-" * 80)
        for pkg in sorted(missing):
            # Tìm import name gốc
            import_name = next((k for k, v in IMPORT_TO_PACKAGE.items() if v == pkg), pkg)
            if import_name in third_party_imports:
                example_files = third_party_imports[import_name][:2]
                print(f"  • {pkg}")
                for f in example_files:
                    rel_path = os.path.relpath(f, project_root)
                    print(f"    └─ Dùng trong: {rel_path}")
        print()
    else:
        print("✅ Không có package nào thiếu!\n")
    
    # 2. Packages trong requirements nhưng KHÔNG được import (có thể thừa)
    unused = all_requirements - required_packages
    
    # Bỏ qua một số packages đặc biệt (dependencies của các package khác)
    exceptions = {
        'gunicorn', 'whitenoise', 'daphne',  # Web servers
        'flower', 'django-celery-results',  # Celery tools
        'mysqlclient', 'pymysql',  # Database drivers
        'django-cors-headers', 'django-oauth-toolkit',  # Django plugins
        'gevent', 'eventlet',  # Async libraries
        'channels-redis',  # Channels backend
        'psycopg2', 'psycopg2-binary',  # PostgreSQL (nếu có)
    }
    
    unused = unused - exceptions
    
    if unused:
        print("⚠️  Có trong requirements.txt nhưng KHÔNG thấy import:")
        print("-" * 80)
        for pkg in sorted(unused):
            print(f"  • {pkg}")
        print()
        print("💡 Lưu ý: Một số packages có thể là:")
        print("   - Dependencies tự động của packages khác")
        print("   - Dùng qua CLI (không import trực tiếp)")
        print("   - Dùng trong production (gunicorn, whitenoise, etc.)")
        print()
    
    # 3. Top imports được sử dụng nhiều nhất
    print("=" * 80)
    print("📈 TOP 20 IMPORTS ĐƯỢC DÙNG NHIỀU NHẤT")
    print("=" * 80)
    sorted_imports = sorted(third_party_imports.items(), 
                           key=lambda x: len(x[1]), reverse=True)[:20]
    
    for i, (module, files) in enumerate(sorted_imports, 1):
        package = IMPORT_TO_PACKAGE.get(module, module)
        in_req = "✅" if package.lower() in all_requirements else "❌"
        print(f"{i:2}. {in_req} {module:20} (dùng trong {len(files):3} files)")
    
    print()
    print("=" * 80)
    print("🎯 TÓM TẮT")
    print("=" * 80)
    print(f"Total packages trong requirements: {len(all_requirements)}")
    print(f"Total third-party imports tìm thấy: {len(third_party_imports)}")
    print(f"Packages thiếu: {len(missing)}")
    print(f"Packages không dùng (có thể): {len(unused)}")
    print()
    
    if missing:
        print("💡 KHUYẾN NGHỊ: Thêm các packages sau vào requirements.txt:")
        print("pip install " + " ".join(sorted(missing)))
        print()


if __name__ == '__main__':
    main()
