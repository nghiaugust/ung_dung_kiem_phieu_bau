"""
API Views - Endpoints cho TrOCR và YOLO
"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import gc
from .model_services import TrOCRService, YOLOService


# Khởi tạo services (singleton - chỉ tạo 1 lần)
trocr_service = TrOCRService()
yolo_service = YOLOService()


@csrf_exempt
@require_http_methods(["POST"])
def trocr_recognize(request):
    """
    API nhận diện text bằng TrOCR
    
    POST /api/trocr/recognize/
    Content-Type: multipart/form-data
    
    Form data:
        - images: Multiple files
    
    Response:
        {
            "success": true,
            "count": 2,
            "results": [
                {
                    "filename": "image1.jpg",
                    "text": "Nguyen Van A",
                    "status": "success"
                },
                ...
            ]
        }
    """
    try:
        # Lấy danh sách ảnh từ request
        files = request.FILES.getlist('images')
        
        if not files:
            return JsonResponse({
                'success': False,
                'error': 'Không có ảnh nào được gửi lên'
            }, status=400)
        
        # Prepare batch
        images = []
        for file in files:
            image_data = file.read()
            filename = file.name
            images.append((image_data, filename))
        
        # Process batch
        print(f"[TrOCR Service] Processing {len(images)}")
        results = trocr_service.recognize_batch(images)
        
        # QUAN TRỌNG: Sort lại results theo index từ filename (format: 0000_1_2.jpg)
        def get_index_from_filename(result):
            try:
                filename = result.get('filename', '')
                if '_' in filename:
                    return int(filename.split('_')[0])
                return 9999
            except:
                return 9999
        
        results = sorted(results, key=get_index_from_filename)
        
        # CLEANUP: Xóa images data sau khi xử lý xong
        del images
        gc.collect()
        
        # Response
        return JsonResponse({
            'success': True,
            'count': len(results),
            'results': results
        })
        
    except Exception as e:
        # Cleanup on error
        gc.collect()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def yolo_detect(request):
    """
    API detect dấu X bằng YOLO
    
    POST /api/yolo/detect/
    Content-Type: multipart/form-data
    
    Form data:
        - images: Multiple files
        - image_paths: JSON string chứa mapping {filename: path} (optional)
    
    Response:
        {
            "success": true,
            "count": 2,
            "results": [
                {
                    "filename": "image1.jpg",
                    "label": "x_mark",
                    "detections": [
                        {
                            "class": "x_mark",
                            "confidence": 0.95,
                            "bbox": [x1, y1, x2, y2]
                        }
                    ],
                    "status": "success"
                },
                ...
            ]
        }
    """
    try:
        # Lấy danh sách ảnh từ request
        files = request.FILES.getlist('images')
        
        if not files:
            return JsonResponse({
                'success': False,
                'error': 'Không có ảnh nào được gửi lên'
            }, status=400)
        
        # Lấy image_paths mapping (nếu có)
        image_paths_json = request.POST.get('image_paths', '{}')
        try:
            image_paths_map = json.loads(image_paths_json)
        except:
            image_paths_map = {}
        
        # Prepare batch
        images = []
        for file in files:
            image_data = file.read()
            filename = file.name
            image_path = image_paths_map.get(filename)
            
            if image_path:
                images.append((image_data, filename, image_path))
            else:
                images.append((image_data, filename))
        
        # Process batch
        results = yolo_service.detect_batch(images)
        
        # QUAN TRỌNG: Sort lại results theo index từ filename (format: 0000_1_2.jpg)
        # Để đảm bảo thứ tự trả về giống với thứ tự gửi đi
        def get_index_from_filename(result):
            try:
                filename = result.get('filename', '')
                # Parse index từ prefix (VD: "0000_1_2.jpg" -> 0)
                if '_' in filename:
                    return int(filename.split('_')[0])
                return 9999  # Fallback nếu không parse được
            except:
                return 9999
        
        results = sorted(results, key=get_index_from_filename)
        
        # CLEANUP: Xóa images data sau khi xử lý xong
        del images
        gc.collect()
        
        # Response
        return JsonResponse({
            'success': True,
            'count': len(results),
            'results': results
        })
        
    except Exception as e:
        # Cleanup on error
        gc.collect()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def health_check(request):
    """
    Health check endpoint
    
    GET /api/health/
    """
    return JsonResponse({
        'status': 'healthy',
        'services': {
            'trocr': trocr_service._pipe is not None,
            'yolo': yolo_service._model is not None
        }
    })


@require_http_methods(["GET"])
def model_info(request):
    """
    Thông tin về models
    
    GET /api/info/
    """
    import torch
    
    return JsonResponse({
        'models': {
            'trocr': {
                'loaded': trocr_service._pipe is not None,
                'device': 'GPU' if torch.cuda.is_available() else 'CPU'
            },
            'yolo': {
                'loaded': yolo_service._model is not None,
                'device': 'GPU' if torch.cuda.is_available() else 'CPU'
            }
        },
        'system': {
            'cuda_available': torch.cuda.is_available(),
            'cuda_device_count': torch.cuda.device_count() if torch.cuda.is_available() else 0
        }
    })
