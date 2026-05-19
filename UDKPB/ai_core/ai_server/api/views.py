"""
API endpoints for model_vietnameocr, model_yolo_x and model_resnet18_crossed.
"""
from __future__ import annotations

import gc
import json

import torch
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .model_services import ResNet18CrossedService, VietNameOCRService, YOLOXService


vietnameocr_service = VietNameOCRService()
yolo_x_service = YOLOXService()
resnet18_crossed_service = ResNet18CrossedService()


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
        images, error_response = _collect_images(request)
        if error_response:
            return error_response

        results = vietnameocr_service.recognize_batch(images)
        results = _sort_results_by_filename_index(results)

        del images
        gc.collect()

        return JsonResponse({"success": True, "count": len(results), "results": results})
    except Exception as exc:
        gc.collect()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def yolo_x_detect(request):
    """
    POST /api/model_yolo_x/detect/
    Form data:
      - images: multiple files
      - image_paths: optional JSON mapping {filename: path}
    """
    try:
        files = request.FILES.getlist("images")
        if not files:
            return JsonResponse(
                {"success": False, "error": "Khong co anh nao duoc gui len"},
                status=400,
            )

        try:
            image_paths_map = json.loads(request.POST.get("image_paths", "{}"))
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

        results = yolo_x_service.detect_batch(images)
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
        images, error_response = _collect_images(request)
        if error_response:
            return error_response

        results = resnet18_crossed_service.detect_batch(images)
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
            "services": {
                "model_vietnameocr": vietnameocr_service._model is not None,
                "model_yolo_x": yolo_x_service._model is not None,
                "model_resnet18_crossed": resnet18_crossed_service._cnn_model is not None,
            },
        }
    )


@require_http_methods(["GET"])
def model_info(request):
    device = "GPU" if torch.cuda.is_available() else "CPU"
    return JsonResponse(
        {
            "models": {
                "model_vietnameocr": {
                    "loaded": vietnameocr_service._model is not None,
                    "device": device,
                },
                "model_yolo_x": {
                    "loaded": yolo_x_service._model is not None,
                    "device": device,
                },
                "model_resnet18_crossed": {
                    "loaded": resnet18_crossed_service._cnn_model is not None,
                    "device": str(resnet18_crossed_service._device),
                    "mode": resnet18_crossed_service._mode,
                },
            },
            "system": {
                "cuda_available": torch.cuda.is_available(),
                "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            },
        }
    )
