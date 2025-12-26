"""
Simple Upload API for Benchmark Testing
Thêm view này vào views.py hoặc import từ file này
"""
import uuid
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings


@csrf_exempt
@require_http_methods(["POST"])
def api_test_upload(request):
    """
    API đơn giản để test hiệu suất upload (không cần authentication)
    Chỉ dùng cho benchmark testing

    Hỗ trợ upload nhiều files cùng lúc
    
    POST /api/test-upload/
    Body: multipart/form-data
        - file: file ảnh (có thể nhiều files)
    
    Response:
    {
        "success": true,
        "total_files": 10,
        "uploaded_files": [
            {
                "filename": "test_file_1.jpg",
                "size": 102400
            },
            ...
        ],
        "total_size": 1024000,
        "message": "Upload thành công"
    }
    """
    try:
        # Check files - hỗ trợ nhiều files
        uploaded_files = request.FILES.getlist('file')
        
        if not uploaded_files:
            return JsonResponse({
                'success': False,
                'error': 'No file provided',
                'message': 'Không có file được gửi lên'
            }, status=400)
        
        # Validate file size (max 10MB per file)
        max_size = 10 * 1024 * 1024  # 10MB
        
        # Tạo thư mục test nếu chưa có
        test_dir = os.path.join(settings.MEDIA_ROOT, 'benchmark_test')
        os.makedirs(test_dir, exist_ok=True)
        
        uploaded_file_info = []
        total_size = 0
        
        # Process each file
        for uploaded_file in uploaded_files:
            # Validate file size
            if uploaded_file.size > max_size:
                return JsonResponse({
                    'success': False,
                    'error': 'File too large',
                    'message': f'File {uploaded_file.name} vượt quá kích thước cho phép ({max_size / 1024 / 1024}MB)'
                }, status=400)
            
            # Tạo tên file unique
            file_ext = uploaded_file.name.split('.')[-1] if '.' in uploaded_file.name else 'bin'
            unique_filename = f"{uuid.uuid4().hex[:8]}_{uploaded_file.name}"
            file_path = os.path.join(test_dir, unique_filename)
            
            # Lưu file
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            # Add to result
            uploaded_file_info.append({
                'filename': unique_filename,
                'original_filename': uploaded_file.name,
                'size': uploaded_file.size,
                'size_mb': round(uploaded_file.size / 1024 / 1024, 2)
            })
            
            total_size += uploaded_file.size
        
        return JsonResponse({
            'success': True,
            'total_files': len(uploaded_files),
            'uploaded_files': uploaded_file_info,
            'total_size': total_size,
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'message': f'Upload thành công {len(uploaded_files)} files'
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Server error',
            'message': str(e)
        }, status=500)
