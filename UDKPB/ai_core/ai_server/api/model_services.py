"""
Model services for the AI server.

Only three models are loaded here:
- model_vietnameocr: OCR for candidate names.
- model_resnet18_x: X-mark classification.
- model_resnet18_crossed: crossed-name classification.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import os
import torch
from PIL import Image, ImageOps

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


class BaseResNet18ClassifierService:
    """Singleton base service for local ResNet18 classifier packages."""

    _instance = None
    _cnn_model = None
    _svm_model = None
    _transform = None
    _device = None
    _names = None
    _predict_module = None
    _mode = "cnn"
    model_key = ""
    model_dir_name = ""
    module_name = ""
    error_label = "unknown"

    def __new__(cls):
        if "_instance" not in cls.__dict__:
            cls._instance = None
        if cls._instance is None:
            cls._instance = super(BaseResNet18ClassifierService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._cnn_model is None:
            self._load_model()

    def _load_model(self):
        try:
            if not self.model_key or not self.model_dir_name or not self.module_name:
                raise RuntimeError("ResNet18 service is missing model metadata")

            model_dir = _ai_core_dir() / self.model_dir_name
            config_path = model_dir / "config.yaml"
            predict_path = model_dir / "predict.py"

            if not config_path.exists():
                raise RuntimeError(f"Cannot find {self.model_key} config: {config_path}")

            module = _load_module(self.module_name, predict_path)
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

            print(f"[{self.model_key}] Loaded in {self._mode} mode on {self._device}")
        except Exception as exc:
            print(f"[{self.model_key}] Failed to load model: {exc}")
            raise

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

    def _probability_payload(self, probabilities=None):
        confidence = 0
        probability_map = {}
        if probabilities is not None:
            probability_map = {
                name: float(prob)
                for name, prob in zip(self._names, probabilities)
            }
            confidence = float(max(probabilities))

        return confidence, probability_map

    def _format_success_result(
        self,
        filename: str,
        raw_label: str,
        confidence: float,
        probability_map: Dict,
    ) -> Dict:
        raise NotImplementedError

    def _parse_prediction(self, filename: str, pred: int, probabilities=None) -> Dict:
        raw_label = self._names[int(pred)]
        confidence, probability_map = self._probability_payload(probabilities)
        return self._format_success_result(filename, raw_label, confidence, probability_map)

    def _format_error_result(self, filename: str, error: str) -> Dict:
        return {
            "filename": filename,
            "label": self.error_label,
            "raw_label": "",
            "confidence": 0,
            "probabilities": {},
            "detections": [],
            "status": "error",
            "error": error,
        }

    def detect(self, image_data: bytes, filename: str = "") -> Dict:
        try:
            return self.detect_batch([(image_data, filename)])[0]
        except Exception as exc:
            return self._format_error_result(filename, str(exc))

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
                results.append(self._format_error_result(filename, f"Image read error: {exc}"))
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


class ResNet18XService(BaseResNet18ClassifierService):
    """Singleton service for model_resnet18_x."""

    _instance = None
    model_key = "model_resnet18_x"
    model_dir_name = "model_resnet18_x"
    module_name = "model_resnet18_x_predict"
    error_label = "unknown"

    @staticmethod
    def _normalize_label(raw_label: str) -> tuple[str, bool, bool]:
        normalized = raw_label.strip().lower()
        if normalized in {"x_mark", "mark", "marked"}:
            return "x_mark", True, False
        if normalized in {"x_cancel", "x_cancelled", "cancel", "cancelled"}:
            return "x_cancel", False, True
        if normalized in {"no_x", "none", "no_mark", "blank"}:
            return "none", False, False
        return normalized or "unknown", False, False

    def _format_success_result(
        self,
        filename: str,
        raw_label: str,
        confidence: float,
        probability_map: Dict,
    ) -> Dict:
        label, is_marked, is_cancelled = self._normalize_label(raw_label)
        return {
            "filename": filename,
            "label": label,
            "raw_label": raw_label,
            "is_marked": is_marked,
            "is_cancelled": is_cancelled,
            "confidence": confidence,
            "probabilities": probability_map,
            "detections": [],
            "status": "success",
        }

    def _format_error_result(self, filename: str, error: str) -> Dict:
        result = super()._format_error_result(filename, error)
        result.update({"is_marked": None, "is_cancelled": None})
        return result


class ResNet18CrossedService(BaseResNet18ClassifierService):
    """Singleton service for model_resnet18_crossed."""

    _instance = None
    model_key = "model_resnet18_crossed"
    model_dir_name = "model_resnet18_crossed"
    module_name = "model_resnet18_crossed_predict"
    error_label = "unknown"

    @staticmethod
    def _normalize_label(raw_label: str) -> tuple[str, bool]:
        normalized = raw_label.strip().lower()
        is_struck = normalized in {"gach_ten", "struck", "crossed_out", "name_struck"}
        return ("struck" if is_struck else "not_struck"), is_struck

    def _format_success_result(
        self,
        filename: str,
        raw_label: str,
        confidence: float,
        probability_map: Dict,
    ) -> Dict:
        label, is_struck = self._normalize_label(raw_label)
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

    def _format_error_result(self, filename: str, error: str) -> Dict:
        result = super()._format_error_result(filename, error)
        result.update({"is_struck": None})
        return result


MODEL_VIETNAMEOCR = "model_vietnameocr"
MODEL_RESNET18_X = "model_resnet18_x"
MODEL_RESNET18_CROSSED = "model_resnet18_crossed"

MODEL_SERVICE_CLASSES = {
    MODEL_VIETNAMEOCR: VietNameOCRService,
    MODEL_RESNET18_X: ResNet18XService,
    MODEL_RESNET18_CROSSED: ResNet18CrossedService,
}


def get_enabled_model_keys() -> List[str]:
    raw_value = os.getenv("AI_ENABLED_MODELS", "all").strip()
    if not raw_value or raw_value.lower() in {"all", "*"}:
        return list(MODEL_SERVICE_CLASSES.keys())

    requested = [item.strip() for item in raw_value.split(",") if item.strip()]
    return [model_key for model_key in requested if model_key in MODEL_SERVICE_CLASSES]
