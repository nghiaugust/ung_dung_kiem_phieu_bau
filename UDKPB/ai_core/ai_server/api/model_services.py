"""
Model services for the AI server.

Only three models are loaded here:
- model_vietnameocr: OCR for candidate names.
- model_yolo_x: X-mark detection.
- model_resnet18_crossed: crossed-name classification.
"""
from __future__ import annotations

import importlib.util
import io
import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
from PIL import Image, ImageOps
from ultralytics import YOLO

warnings.filterwarnings("ignore", category=FutureWarning)


def _ai_core_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_module(module_name: str, module_path: Path, prepend_path: Optional[Path] = None):
    if prepend_path is not None:
        prepend_text = str(prepend_path)
        if prepend_text not in sys.path:
            sys.path.insert(0, prepend_text)

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class VietNameOCRService:
    """Singleton service for model_vietnameocr."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VietNameOCRService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._model is None:
            self._load_model()

    def _load_model(self):
        try:
            model_dir = _ai_core_dir() / "model_vietnameocr" / "VietNameOCR"
            config_path = model_dir / "config_mobilenet_svtr_ctc.yml"
            weights_path = model_dir / "weights" / "mobilenet_svtr_ctc.pth"
            predict_path = model_dir / "predict.py"

            if not config_path.exists():
                raise RuntimeError(f"Cannot find VietNameOCR config: {config_path}")
            if not weights_path.exists():
                raise RuntimeError(f"Cannot find VietNameOCR weights: {weights_path}")

            module = _load_module(
                "model_vietnameocr_predict",
                predict_path,
                prepend_path=model_dir,
            )
            self._model = module.VietNameOCR(str(config_path), str(weights_path))

            device_name = "GPU" if torch.cuda.is_available() else "CPU"
            print(f"[model_vietnameocr] Loaded on {device_name}")
        except Exception as exc:
            print(f"[model_vietnameocr] Failed to load model: {exc}")
            raise

    def recognize_text(self, image_data: bytes, filename: str = "") -> Dict:
        pil_img = None
        try:
            pil_img = Image.open(io.BytesIO(image_data))
            text = self._model.predict(pil_img)
            return {
                "filename": filename,
                "text": text,
                "confidence": 0,
                "status": "success",
            }
        except Exception as exc:
            return {
                "filename": filename,
                "text": "",
                "confidence": 0,
                "status": "error",
                "error": str(exc),
            }
        finally:
            if pil_img is not None:
                pil_img.close()

    def recognize_batch(self, images: List[tuple]) -> List[Dict]:
        return [self.recognize_text(image_data, filename) for image_data, filename in images]


def crop_center_horizontal(pil_img: Image.Image) -> Image.Image:
    width, height = pil_img.size
    left = width // 4
    right = 3 * width // 4
    return pil_img.crop((left, 0, right, height))


class YOLOXService:
    """Singleton service for model_yolo_x."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(YOLOXService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._model is None:
            self._load_model()

    def _load_model(self):
        try:
            model_path = _ai_core_dir() / "model_yolo_x" / "best.pt"
            if not model_path.exists():
                raise RuntimeError(f"Cannot find YOLO weights: {model_path}")

            self._model = YOLO(str(model_path))
            if torch.cuda.is_available():
                self._model.to("cuda")
                print("[model_yolo_x] Loaded on GPU")
            else:
                self._model.to("cpu")
                print("[model_yolo_x] Loaded on CPU")
        except Exception as exc:
            print(f"[model_yolo_x] Failed to load model: {exc}")
            raise

    def _parse_prediction(self, result, filename: str) -> Dict:
        detections = []
        label = "none"

        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes.xyxy.cpu().numpy()
            classes = result.boxes.cls.cpu().numpy()
            confidences = result.boxes.conf.cpu().numpy()
            class_names = result.names

            for box, cls_id, conf in zip(boxes, classes, confidences):
                cls_name = class_names[int(cls_id)]
                detections.append(
                    {
                        "class": cls_name,
                        "confidence": float(conf),
                        "bbox": box.tolist(),
                    }
                )

            if any(det["class"] == "x_mark" for det in detections):
                label = "x_mark"
            elif any(det["class"] == "x_cancelled" for det in detections):
                label = "x_cancelled"

        return {
            "filename": filename,
            "label": label,
            "detections": detections,
            "status": "success",
        }

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
            return self._parse_prediction(results[0], filename)
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
            for item in images:
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
                    results.append(
                        {
                            "filename": filename,
                            "label": "none",
                            "detections": [],
                            "status": "error",
                            "error": f"Image read error: {exc}",
                        }
                    )

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
                    results.append(self._parse_prediction(result, filename))

            return results
        except Exception as exc:
            print(f"[model_yolo_x] Batch failed, fallback to individual: {exc}")
            return [
                self.detect(item[0], item[1], item[2] if len(item) > 2 else None)
                for item in images
            ]
        finally:
            for img in cropped_images:
                img.close()
            for img in pil_images:
                img.close()


class ResNet18CrossedService:
    """Singleton service for model_resnet18_crossed."""

    _instance = None
    _cnn_model = None
    _svm_model = None
    _transform = None
    _device = None
    _names = None
    _predict_module = None
    _mode = "cnn"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ResNet18CrossedService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._cnn_model is None:
            self._load_model()

    def _load_model(self):
        try:
            model_dir = _ai_core_dir() / "model_resnet18_crossed"
            config_path = model_dir / "config.yaml"
            predict_path = model_dir / "predict.py"

            if not config_path.exists():
                raise RuntimeError(f"Cannot find ResNet18 crossed config: {config_path}")

            module = _load_module("model_resnet18_crossed_predict", predict_path)
            cfg = module.load_config(config_path)
            self._predict_module = module
            self._names = module.label_names(cfg)
            self._transform = module.build_transform(cfg)

            device_name = cfg.get("runtime", {}).get("device", "auto")
            self._device = module.get_device(device_name)

            checkpoint_path = module.resolve_path(
                cfg["paths"]["cnn_checkpoint"],
                config_path.parent,
            )
            self._cnn_model = module.load_cnn(
                checkpoint_path,
                num_classes=len(self._names),
                device=self._device,
            )

            self._mode = cfg.get("runtime", {}).get("mode", "cnn")
            if self._mode == "svm":
                svm_path = module.resolve_path(cfg["paths"]["svm_model"], config_path.parent)
                if not svm_path.exists():
                    raise RuntimeError(f"Cannot find SVM model: {svm_path}")
                self._svm_model = module.joblib.load(svm_path)

            print(f"[model_resnet18_crossed] Loaded in {self._mode} mode on {self._device}")
        except Exception as exc:
            print(f"[model_resnet18_crossed] Failed to load model: {exc}")
            raise

    @staticmethod
    def _normalize_label(raw_label: str) -> tuple[str, bool]:
        normalized = raw_label.strip().lower()
        is_struck = normalized in {"gach_ten", "struck", "crossed_out", "name_struck"}
        return ("struck" if is_struck else "not_struck"), is_struck

    def _predict_batch_tensors(self, batch: torch.Tensor):
        if self._mode == "svm":
            features = self._predict_module.extract_features(self._cnn_model, batch, self._device)
            predictions = self._svm_model.predict(features)
            probabilities = (
                self._svm_model.predict_proba(features)
                if hasattr(self._svm_model, "predict_proba")
                else None
            )
            return predictions, probabilities

        return self._predict_module.predict_cnn(self._cnn_model, batch, self._device)

    def _parse_prediction(self, filename: str, pred: int, probabilities=None) -> Dict:
        raw_label = self._names[int(pred)]
        label, is_struck = self._normalize_label(raw_label)

        confidence = 0
        probability_map = {}
        if probabilities is not None:
            probability_map = {
                name: float(prob)
                for name, prob in zip(self._names, probabilities)
            }
            confidence = float(max(probabilities))

        return {
            "filename": filename,
            "label": label,
            "raw_label": raw_label,
            "is_struck": is_struck,
            "confidence": confidence,
            "probabilities": probability_map,
            "detections": [],
            "status": "success",
        }

    def detect(self, image_data: bytes, filename: str = "") -> Dict:
        try:
            return self.detect_batch([(image_data, filename)])[0]
        except Exception as exc:
            return {
                "filename": filename,
                "label": "unknown",
                "raw_label": "",
                "is_struck": None,
                "confidence": 0,
                "probabilities": {},
                "detections": [],
                "status": "error",
                "error": str(exc),
            }

    def detect_batch(self, images: List[tuple]) -> List[Dict]:
        tensors = []
        filenames = []
        results = []

        for image_data, filename in images:
            pil_img = None
            try:
                pil_img = Image.open(io.BytesIO(image_data))
                pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
                tensors.append(self._transform(pil_img))
                filenames.append(filename)
            except Exception as exc:
                results.append(
                    {
                        "filename": filename,
                        "label": "unknown",
                        "raw_label": "",
                        "is_struck": None,
                        "confidence": 0,
                        "probabilities": {},
                        "detections": [],
                        "status": "error",
                        "error": f"Image read error: {exc}",
                    }
                )
            finally:
                if pil_img is not None:
                    pil_img.close()

        if not tensors:
            return results

        batch = torch.stack(tensors, dim=0)
        predictions, probabilities = self._predict_batch_tensors(batch)

        for idx, (filename, pred) in enumerate(zip(filenames, predictions)):
            row_probs = probabilities[idx] if probabilities is not None else None
            results.append(self._parse_prediction(filename, int(pred), row_probs))

        return results
