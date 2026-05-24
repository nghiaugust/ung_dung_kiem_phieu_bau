"""
Model services for VietNameOCR and YOLO.
Models are loaded once when the AI server starts and reused for requests.
"""
import io
import importlib.util
import os
import sys
import warnings
from typing import Dict, List

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

warnings.filterwarnings("ignore", category=FutureWarning)


def _get_ai_core_dir() -> str:
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(current_dir)


def _get_vietnameocr_class():
    vietnameocr_dir = os.path.join(
        _get_ai_core_dir(),
        "model_vietnameocr",
        "VietNameOCR",
    )
    vietnameocr_dir = os.path.normpath(vietnameocr_dir)

    if not os.path.isdir(vietnameocr_dir):
        raise RuntimeError(f"Khong tim thay thu muc VietNameOCR: {vietnameocr_dir}")

    if vietnameocr_dir not in sys.path:
        sys.path.insert(0, vietnameocr_dir)

    module_name = "local_vietnameocr_predict"
    if module_name in sys.modules:
        return sys.modules[module_name].VietNameOCR, vietnameocr_dir

    predict_path = os.path.join(vietnameocr_dir, "predict.py")
    spec = importlib.util.spec_from_file_location(module_name, predict_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Khong the load VietNameOCR predict.py: {predict_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module.VietNameOCR, vietnameocr_dir


class VietNameOCRService:
    """Singleton service for the local VietNameOCR model."""

    _instance = None
    _engine = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VietNameOCRService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._engine is None:
            self._load_model()

    def _load_model(self):
        try:
            VietNameOCR, model_dir = _get_vietnameocr_class()
            config_path = os.path.join(model_dir, "config_mobilenet_svtr_ctc.yml")
            weights_path = os.path.join(model_dir, "weights", "mobilenet_svtr_ctc.pth")

            if not os.path.exists(config_path):
                raise RuntimeError(f"Khong tim thay config VietNameOCR: {config_path}")
            if not os.path.exists(weights_path):
                raise RuntimeError(f"Khong tim thay weights VietNameOCR: {weights_path}")

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            print(f"[VietNameOCR Service] Loading on {device}")
            self._engine = VietNameOCR(config_path, weights_path, device=device)
            print("[VietNameOCR Service] Model loaded")
        except Exception as exc:
            print(f"[VietNameOCR Service] Error loading model: {exc}")
            raise

    def recognize_text(self, image_data: bytes, filename: str = "") -> Dict:
        pil_img = None
        try:
            pil_img = Image.open(io.BytesIO(image_data))
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")

            text = self._engine.predict(pil_img)

            return {
                "filename": filename,
                "text": text,
                "status": "success",
            }
        except Exception as exc:
            return {
                "filename": filename,
                "text": "",
                "status": "error",
                "error": str(exc),
            }
        finally:
            if pil_img is not None:
                pil_img.close()

    def recognize_batch(self, images: List[tuple]) -> List[Dict]:
        results = []
        for image_data, filename in images:
            results.append(self.recognize_text(image_data, filename))
        return results


def crop_center_horizontal(pil_img: Image.Image) -> Image.Image:
    """
    Crop the center half horizontally. This matches the existing YOLO input
    preprocessing used for vote mark cells.
    """
    width, height = pil_img.size
    left = width // 4
    right = 3 * width // 4
    cropped_img = pil_img.crop((left, 0, right, height))
    print(
        f"[Crop] Original: {width}x{height} -> cropped: "
        f"{cropped_img.size[0]}x{cropped_img.size[1]}"
    )
    return cropped_img


class YOLOService:
    """Singleton service for the YOLO vote mark detector."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(YOLOService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._model is None:
            self._load_model()

    def _load_model(self):
        try:
            model_path = os.path.join(_get_ai_core_dir(), "model_yolo_x", "best.pt")
            model_path = os.path.normpath(model_path)

            if not os.path.exists(model_path):
                raise RuntimeError(f"Khong tim thay YOLO weights: {model_path}")

            self._model = YOLO(model_path)

            if torch.cuda.is_available():
                self._model.to("cuda")
                print("[YOLO Service] Using GPU")
            else:
                self._model.to("cpu")
                print("[YOLO Service] Using CPU")
        except Exception as exc:
            print(f"[YOLO Service] Error loading model: {exc}")
            raise

    def detect(self, image_data: bytes, filename: str = "", image_path: str = None) -> Dict:
        pil_img = None
        cropped_img = None
        results = None

        try:
            pil_img = Image.open(io.BytesIO(image_data))
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")

            cropped_img = crop_center_horizontal(pil_img)
            img_array = np.array(cropped_img)

            results = self._model.predict(
                source=img_array,
                save=False,
                verbose=False,
                conf=0.25,
                iou=0.45,
            )

            detections, label = self._parse_yolo_result(results[0])

            # Drawing is intentionally disabled; the API returns structured data only.
            # if image_path:
            #     self._draw_detections(pil_img, detections, image_path, label)

            return {
                "filename": filename,
                "label": label,
                "detections": detections,
                "status": "success",
            }
        except Exception as exc:
            return {
                "filename": filename,
                "label": "none",
                "detections": [],
                "status": "error",
                "error": str(exc),
            }
        finally:
            if cropped_img is not None:
                cropped_img.close()
            if pil_img is not None:
                pil_img.close()
            if results is not None:
                del results

    def detect_batch(self, images: List[tuple]) -> List[Dict]:
        results = []
        pil_images = []
        cropped_images = []
        img_arrays = []
        filenames = []

        try:
            print(f"[YOLO Service] Batch processing {len(images)} images")

            for item in images:
                if len(item) == 3:
                    image_data, filename, _image_path = item
                else:
                    image_data, filename = item[:2]

                try:
                    pil_img = Image.open(io.BytesIO(image_data))
                    if pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")
                    pil_images.append(pil_img)

                    cropped_img = crop_center_horizontal(pil_img)
                    cropped_images.append(cropped_img)
                    img_arrays.append(np.array(cropped_img))
                    filenames.append(filename)
                except Exception as exc:
                    results.append({
                        "filename": filename,
                        "label": "none",
                        "detections": [],
                        "status": "error",
                        "error": f"Loi doc anh: {exc}",
                    })

            if img_arrays:
                batch_results = self._model.predict(
                    source=img_arrays,
                    save=False,
                    verbose=False,
                    conf=0.25,
                    iou=0.45,
                    stream=False,
                )

                for filename, result in zip(filenames, batch_results):
                    detections, label = self._parse_yolo_result(result)
                    results.append({
                        "filename": filename,
                        "label": label,
                        "detections": detections,
                        "status": "success",
                    })

                del batch_results
                print(f"[YOLO Service] Batch processed {len(results)} images")
        except Exception as exc:
            print(f"[YOLO Service] Batch failed, fallback to individual: {exc}")
            results = []
            for item in images:
                if len(item) == 3:
                    image_data, filename, image_path = item
                    results.append(self.detect(image_data, filename, image_path))
                else:
                    image_data, filename = item[:2]
                    results.append(self.detect(image_data, filename))
        finally:
            for img in cropped_images:
                try:
                    img.close()
                except Exception:
                    pass
            for img in pil_images:
                try:
                    img.close()
                except Exception:
                    pass

        return results

    def _parse_yolo_result(self, result):
        detections = []
        label = "none"

        if result.boxes is None or len(result.boxes) == 0:
            return detections, label

        boxes = result.boxes.xyxy.cpu().numpy()
        classes = result.boxes.cls.cpu().numpy()
        confidences = result.boxes.conf.cpu().numpy()
        class_names = result.names

        for box, cls_id, conf in zip(boxes, classes, confidences):
            cls_name = class_names[int(cls_id)]
            detections.append({
                "class": cls_name,
                "confidence": float(conf),
                "bbox": box.tolist(),
            })

        has_x_mark = any(d["class"] == "x_mark" for d in detections)
        has_x_cancelled = any(d["class"] == "x_cancelled" for d in detections)

        if has_x_mark:
            label = "x_mark"
        elif has_x_cancelled:
            label = "x_cancelled"

        return detections, label

    def _draw_detections(
        self,
        pil_img: Image.Image,
        detections: List[Dict],
        image_path: str,
        label: str = "none",
    ):
        draw = None
        font = None

        try:
            draw = ImageDraw.Draw(pil_img)

            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except Exception:
                font = ImageFont.load_default()

            if not detections or label == "none":
                text = "none (0%)"
                text_bbox = draw.textbbox((10, 10), text, font=font)
                draw.rectangle(text_bbox, fill=(128, 128, 128))
                draw.text((10, 10), text, fill=(255, 255, 255), font=font)
            else:
                color_map = {
                    "x_mark": (0, 255, 0),
                    "x_cancelled": (255, 0, 0),
                }

                for det in detections:
                    bbox = det["bbox"]
                    cls_name = det["class"]
                    conf = det["confidence"]
                    color = color_map.get(cls_name, (255, 255, 0))
                    draw.rectangle(bbox, outline=color, width=3)
                    label_text = f"{cls_name}: {conf:.0%}"
                    text_bbox = draw.textbbox((bbox[0], bbox[1] - 25), label_text, font=font)
                    draw.rectangle(text_bbox, fill=color)
                    draw.text((bbox[0], bbox[1] - 25), label_text, fill=(255, 255, 255), font=font)

            pil_img.save(image_path)
            print(f"[YOLO Service] Saved detection image: {os.path.basename(image_path)}")
        except Exception as exc:
            print(f"[YOLO Service] Draw detection error: {exc}")
        finally:
            del draw, font
            if pil_img is not None:
                pil_img.close()


MODEL_VIETNAMEOCR = "model_vietnameocr"
MODEL_YOLO_X = "model_yolo_x"

MODEL_SERVICE_CLASSES = {
    MODEL_VIETNAMEOCR: VietNameOCRService,
    MODEL_YOLO_X: YOLOService,
}

MODEL_ALIASES = {
    "vietnameocr": MODEL_VIETNAMEOCR,
    MODEL_VIETNAMEOCR: MODEL_VIETNAMEOCR,
    "yolo": MODEL_YOLO_X,
    "yolo_x": MODEL_YOLO_X,
    MODEL_YOLO_X: MODEL_YOLO_X,
}


def get_enabled_model_keys() -> List[str]:
    raw_value = os.getenv("AI_ENABLED_MODELS", "all").strip()
    if not raw_value or raw_value.lower() in {"all", "*"}:
        return list(MODEL_SERVICE_CLASSES.keys())

    requested = []
    for item in raw_value.split(","):
        model_key = MODEL_ALIASES.get(item.strip().lower())
        if model_key and model_key not in requested:
            requested.append(model_key)
    return requested
