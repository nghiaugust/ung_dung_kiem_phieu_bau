"""
API views for VietNameOCR and YOLO.
"""
import gc
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .model_services import VietNameOCRService, YOLOService


try:
    vietnameocr_service = VietNameOCRService()
except Exception as exc:
    vietnameocr_service = None
    print(f"[VietNameOCR Service] Skip load (optional): {exc}")

try:
    yolo_service = YOLOService()
except Exception as exc:
    print(f"[YOLO Service] Error loading model: {exc}")
    raise


def _sort_results_by_filename_index(results):
    def get_index_from_filename(result):
        try:
            filename = result.get("filename", "")
            if "_" in filename:
                return int(filename.split("_")[0])
        except Exception:
            pass
        return 9999

    return sorted(results, key=get_index_from_filename)


@csrf_exempt
@require_http_methods(["POST"])
def vietnameocr_recognize(request):
    """
    Recognize text with VietNameOCR.

    POST /api/vietnameocr/recognize/
    Content-Type: multipart/form-data
    Form data:
        - images: multiple files
    """
    try:
        if vietnameocr_service is None:
            return JsonResponse({
                "success": False,
                "error": "VietNameOCR model chua duoc nap",
            }, status=503)

        files = request.FILES.getlist("images")
        if not files:
            return JsonResponse({
                "success": False,
                "error": "Khong co anh nao duoc gui len",
            }, status=400)

        images = [(file.read(), file.name) for file in files]
        print(f"[VietNameOCR Service] Processing {len(images)} images")

        results = vietnameocr_service.recognize_batch(images)
        results = _sort_results_by_filename_index(results)

        del images
        gc.collect()

        return JsonResponse({
            "success": True,
            "count": len(results),
            "results": results,
        })
    except Exception as exc:
        gc.collect()
        return JsonResponse({
            "success": False,
            "error": str(exc),
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def yolo_detect(request):
    """
    Detect vote marks with YOLO.

    POST /api/yolo/detect/
    Content-Type: multipart/form-data
    Form data:
        - images: multiple files
        - image_paths: JSON mapping {filename: path} (optional)
    """
    try:
        files = request.FILES.getlist("images")
        if not files:
            return JsonResponse({
                "success": False,
                "error": "Khong co anh nao duoc gui len",
            }, status=400)

        image_paths_json = request.POST.get("image_paths", "{}")
        try:
            image_paths_map = json.loads(image_paths_json)
        except Exception:
            image_paths_map = {}

        images = []
        for file in files:
            image_data = file.read()
            filename = file.name
            image_path = image_paths_map.get(filename)
            if image_path:
                images.append((image_data, filename, image_path))
            else:
                images.append((image_data, filename))

        results = yolo_service.detect_batch(images)
        results = _sort_results_by_filename_index(results)

        del images
        gc.collect()

        return JsonResponse({
            "success": True,
            "count": len(results),
            "results": results,
        })
    except Exception as exc:
        gc.collect()
        return JsonResponse({
            "success": False,
            "error": str(exc),
        }, status=500)


@require_http_methods(["GET", "HEAD"])
def health_check(request):
    vietnameocr_loaded = (
        vietnameocr_service is not None
        and vietnameocr_service._engine is not None
    )
    yolo_loaded = yolo_service is not None and yolo_service._model is not None

    return JsonResponse({
        "status": "healthy",
        "services": {
            "vietnameocr": vietnameocr_loaded,
            "yolo": yolo_loaded,
        },
    })


@require_http_methods(["GET"])
def model_info(request):
    import torch

    vietnameocr_loaded = (
        vietnameocr_service is not None
        and vietnameocr_service._engine is not None
    )
    yolo_loaded = yolo_service is not None and yolo_service._model is not None

    return JsonResponse({
        "models": {
            "vietnameocr": {
                "loaded": vietnameocr_loaded,
                "device": "GPU" if torch.cuda.is_available() else "CPU",
            },
            "yolo": {
                "loaded": yolo_loaded,
                "device": "GPU" if torch.cuda.is_available() else "CPU",
            },
        },
        "system": {
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        },
    })
