import difflib
import unicodedata


RESNET_CONF_HIGH = 0.90
RESNET_MARGIN_HIGH = 0.25
SVM_CONF_HIGH = 0.80
OCR_GOOD = 0.88
OCR_BAD = 0.75
VISUAL_CROSSED_STRONG = 0.85
VISUAL_NOT_CROSSED_STRONG = 0.85

CROSSED_LABEL = "crossed"
NOT_CROSSED_LABEL = "not_crossed"


def get_cascade_request_data():
    return {
        "cascade": "1",
        "resnet_conf_high": str(RESNET_CONF_HIGH),
        "resnet_margin_high": str(RESNET_MARGIN_HIGH),
        "svm_conf_high": str(SVM_CONF_HIGH),
    }


def normalize_crossed_label(raw_label):
    normalized = str(raw_label or "").strip().lower()
    if normalized in {"gach_ten", "crossed", "crossed_out", "name_crossed"}:
        return CROSSED_LABEL
    if normalized in {"ten", "not_crossed", "khong_gach_ten", "clear", "normal"}:
        return NOT_CROSSED_LABEL
    return normalized or "unknown"


def is_crossed_result(result_data):
    if not isinstance(result_data, dict):
        return False

    is_crossed = result_data.get("is_crossed")
    if isinstance(is_crossed, bool):
        return is_crossed

    return normalize_crossed_label(result_data.get("label")) == CROSSED_LABEL


def has_crossed_decision(result_data):
    if not isinstance(result_data, dict):
        return False
    if isinstance(result_data.get("is_crossed"), bool):
        return True
    return normalize_crossed_label(result_data.get("label")) in {CROSSED_LABEL, NOT_CROSSED_LABEL}


def is_error_result(result_data):
    if isinstance(result_data, str):
        return result_data.startswith("[")
    if isinstance(result_data, dict):
        return bool(result_data.get("error")) or not has_crossed_decision(result_data)
    return result_data is None


def needs_ocr(visual_result):
    if not isinstance(visual_result, dict):
        return False
    return bool(visual_result.get("needs_review")) or visual_result.get("decision_stage") == "visual_fallback"


def _normalize_text(text):
    text = unicodedata.normalize("NFD", str(text or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("Đ", "D").replace("đ", "d")
    text = "".join(ch if ch.isalnum() else " " for ch in text)
    return " ".join(text.upper().split())


def name_similarity(ocr_text, candidate_name):
    normalized_ocr = _normalize_text(ocr_text)
    normalized_candidate = _normalize_text(candidate_name)
    if not normalized_ocr or not normalized_candidate:
        return 0.0
    return difflib.SequenceMatcher(None, normalized_ocr, normalized_candidate).ratio()


def _ocr_text(ocr_result):
    if isinstance(ocr_result, dict):
        if "text" in ocr_result:
            return str(ocr_result.get("text") or "")
        return str(ocr_result.get("result") or "")
    return str(ocr_result or "")


def _visual_confidence(visual_result):
    try:
        return float(visual_result.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def build_crossed_result(visual_result, ocr_result=None, candidate_name=""):
    visual_result = visual_result if isinstance(visual_result, dict) else {}
    ocr_result = ocr_result if isinstance(ocr_result, dict) else {}
    label = normalize_crossed_label(visual_result.get("label") or visual_result.get("raw_label"))
    is_crossed = label == CROSSED_LABEL
    visual_confidence = _visual_confidence(visual_result)
    decision_stage = visual_result.get("decision_stage") or "resnet18"
    needs_review = bool(visual_result.get("needs_review", False))

    ocr_text = _ocr_text(ocr_result)
    similarity = name_similarity(ocr_text, candidate_name)
    final_label = label
    final_confidence = visual_confidence
    final_stage = decision_stage
    final_needs_review = needs_review

    if needs_review:
        if (
            label == NOT_CROSSED_LABEL
            and visual_confidence >= VISUAL_NOT_CROSSED_STRONG
            and similarity >= OCR_GOOD
        ):
            final_label = NOT_CROSSED_LABEL
            final_confidence = max(visual_confidence, similarity)
            final_stage = "ocr"
            final_needs_review = False
        elif (
            label == CROSSED_LABEL
            and visual_confidence >= VISUAL_CROSSED_STRONG
            and similarity < OCR_BAD
        ):
            final_label = CROSSED_LABEL
            final_confidence = visual_confidence
            final_stage = "ocr"
            final_needs_review = False

    return {
        "label": final_label,
        "raw_label": visual_result.get("raw_label", ""),
        "is_crossed": final_label == CROSSED_LABEL,
        "confidence": final_confidence,
        "decision_stage": final_stage,
        "needs_review": final_needs_review,
        "candidate_name": candidate_name or "",
        "ocr": {
            "used": "text" in ocr_result or "result" in ocr_result,
            "text": ocr_text,
            "similarity": similarity,
            "confidence": ocr_result.get("confidence", 0),
        },
        "model_outputs": visual_result.get("model_outputs", {}),
        "probabilities": visual_result.get("probabilities", {}),
        "detections": visual_result.get("detections", []),
    }
