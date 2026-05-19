"""
API endpoints for model_vietnameocr, model_resnet18_x and model_resnet18_crossed.
"""
from __future__ import annotations

import gc

import torch
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .model_services import (
    MODEL_RESNET18_CROSSED,
    MODEL_RESNET18_X,
    MODEL_SERVICE_CLASSES,
    MODEL_VIETNAMEOCR,
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
    service = _get_service(model_key)
    if service is None:
        return False
    if model_key == MODEL_VIETNAMEOCR:
        return service._model is not None
    return service._cnn_model is not None


def _disabled_model_response(model_key):
    return JsonResponse(
        {
            "success": False,
            "error": f"{model_key} is not enabled in this AI server process",
        },
        status=503,
    )


def _collect_images(request):
    files = request.FILES.getlist("images")
    if not files:
        return None, JsonResponse(
            {"success": False, "error": "Khong co anh nao duoc gui len"},
            status=400,
        )

    images = []
    for file in files:
        images.append((file.read(), file.name))
    return images, None


def _sort_results_by_filename_index(results):
    def get_index(result):
        try:
            filename = result.get("filename", "")
            if "_" in filename:
                return int(filename.split("_")[0])
        except Exception:
            pass
        return 9999

    return sorted(results, key=get_index)


@csrf_exempt
@require_http_methods(["POST"])
def vietnameocr_recognize(request):
    """
    POST /api/model_vietnameocr/recognize/
    Form data:
      - images: multiple files
    """
    try:
        service = _get_service(MODEL_VIETNAMEOCR)
        if service is None:
            return _disabled_model_response(MODEL_VIETNAMEOCR)

        images, error_response = _collect_images(request)
        if error_response:
            return error_response

        results = service.recognize_batch(images)
        results = _sort_results_by_filename_index(results)

        del images
        gc.collect()

        return JsonResponse({"success": True, "count": len(results), "results": results})
    except Exception as exc:
        gc.collect()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def resnet18_x_detect(request):
    """
    POST /api/model_resnet18_x/detect/
    Form data:
      - images: multiple files
    """
    try:
        service = _get_service(MODEL_RESNET18_X)
        if service is None:
            return _disabled_model_response(MODEL_RESNET18_X)

        images, error_response = _collect_images(request)
        if error_response:
            return error_response

        results = service.detect_batch(images)
        results = _sort_results_by_filename_index(results)

        del images
        gc.collect()

        return JsonResponse({"success": True, "count": len(results), "results": results})
    except Exception as exc:
        gc.collect()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def resnet18_crossed_detect(request):
    """
    POST /api/model_resnet18_crossed/detect/
    Form data:
      - images: multiple files
    """
    try:
        service = _get_service(MODEL_RESNET18_CROSSED)
        if service is None:
            return _disabled_model_response(MODEL_RESNET18_CROSSED)

        images, error_response = _collect_images(request)
        if error_response:
            return error_response

        results = service.detect_batch(images)
        results = _sort_results_by_filename_index(results)

        del images
        gc.collect()

        return JsonResponse({"success": True, "count": len(results), "results": results})
    except Exception as exc:
        gc.collect()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@require_http_methods(["GET", "HEAD"])
def health_check(request):
    return JsonResponse(
        {
            "status": "healthy",
            "enabled_models": get_enabled_model_keys(),
            "services": {
                MODEL_VIETNAMEOCR: _service_loaded(MODEL_VIETNAMEOCR),
                MODEL_RESNET18_X: _service_loaded(MODEL_RESNET18_X),
                MODEL_RESNET18_CROSSED: _service_loaded(MODEL_RESNET18_CROSSED),
            },
        }
    )


@require_http_methods(["GET"])
def model_info(request):
    device = "GPU" if torch.cuda.is_available() else "CPU"
    vietnameocr_service = _get_service(MODEL_VIETNAMEOCR)
    resnet18_x_service = _get_service(MODEL_RESNET18_X)
    resnet18_crossed_service = _get_service(MODEL_RESNET18_CROSSED)
    return JsonResponse(
        {
            "enabled_models": get_enabled_model_keys(),
            "models": {
                MODEL_VIETNAMEOCR: {
                    "loaded": vietnameocr_service._model is not None if vietnameocr_service else False,
                    "device": device,
                },
                MODEL_RESNET18_X: {
                    "loaded": resnet18_x_service._cnn_model is not None if resnet18_x_service else False,
                    "device": str(resnet18_x_service._device) if resnet18_x_service else "",
                    "mode": resnet18_x_service._mode if resnet18_x_service else "",
                },
                MODEL_RESNET18_CROSSED: {
                    "loaded": resnet18_crossed_service._cnn_model is not None if resnet18_crossed_service else False,
                    "device": str(resnet18_crossed_service._device) if resnet18_crossed_service else "",
                    "mode": resnet18_crossed_service._mode if resnet18_crossed_service else "",
                },
            },
            "system": {
                "cuda_available": torch.cuda.is_available(),
                "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            },
        }
    )
