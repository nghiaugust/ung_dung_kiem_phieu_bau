"""
API views for VietNameOCR and YOLO-X.
"""
import gc
import json

import torch
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .model_services import (
    MODEL_SERVICE_CLASSES,
    MODEL_VIETNAMEOCR,
    MODEL_YOLO_X,
    get_enabled_model_keys,
)


_services = {}


def _get_service(model_key):
    if model_key not in get_enabled_model_keys():
        return None

    if model_key not in _services:
        _services[model_key] = MODEL_SERVICE_CLASSES[model_key]()
    return _services[model_key]


def _service_loaded(model_key):
    try:
        service = _get_service(model_key)
    except Exception:
        return False

    if service is None:
        return False
    if model_key == MODEL_VIETNAMEOCR:
        return service._engine is not None
    if model_key == MODEL_YOLO_X:
        return service._model is not None
    return False


def _disabled_model_response(model_key):
    return JsonResponse(
        {
            "success": False,
            "error": f"{model_key} is not enabled in this AI server process",
        },
        status=503,
    )


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
    POST /api/model_vietnameocr/recognize/
    POST /api/vietnameocr/recognize/ also remains supported.
    """
    try:
        service = _get_service(MODEL_VIETNAMEOCR)
        if service is None:
            return _disabled_model_response(MODEL_VIETNAMEOCR)

        files = request.FILES.getlist("images")
        if not files:
            return JsonResponse({
                "success": False,
                "error": "Khong co anh nao duoc gui len",
            }, status=400)

        images = [(file.read(), file.name) for file in files]
        print(f"[VietNameOCR Service] Processing {len(images)} images")

        results = service.recognize_batch(images)
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
    POST /api/model_yolo_x/detect/
    POST /api/yolo/detect/ also remains supported.
    """
    try:
        service = _get_service(MODEL_YOLO_X)
        if service is None:
            return _disabled_model_response(MODEL_YOLO_X)

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

        results = service.detect_batch(images)
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
    vietnameocr_loaded = _service_loaded(MODEL_VIETNAMEOCR)
    yolo_loaded = _service_loaded(MODEL_YOLO_X)

    return JsonResponse({
        "status": "healthy",
        "enabled_models": get_enabled_model_keys(),
        "services": {
            MODEL_VIETNAMEOCR: vietnameocr_loaded,
            MODEL_YOLO_X: yolo_loaded,
            "vietnameocr": vietnameocr_loaded,
            "yolo": yolo_loaded,
        },
    })


@require_http_methods(["GET"])
def model_info(request):
    vietnameocr_loaded = _service_loaded(MODEL_VIETNAMEOCR)
    yolo_loaded = _service_loaded(MODEL_YOLO_X)
    device = "GPU" if torch.cuda.is_available() else "CPU"

    return JsonResponse({
        "enabled_models": get_enabled_model_keys(),
        "models": {
            MODEL_VIETNAMEOCR: {
                "loaded": vietnameocr_loaded,
                "device": device,
            },
            MODEL_YOLO_X: {
                "loaded": yolo_loaded,
                "device": device,
            },
            "vietnameocr": {
                "loaded": vietnameocr_loaded,
                "device": device,
            },
            "yolo": {
                "loaded": yolo_loaded,
                "device": device,
            },
        },
        "system": {
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        },
    })
