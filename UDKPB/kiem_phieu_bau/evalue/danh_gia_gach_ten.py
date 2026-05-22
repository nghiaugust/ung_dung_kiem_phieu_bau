import json
import logging
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from ballot.models import Ballot, BallotSelection
from counting import config_crossed
from counting.models import AIModelResult
from poll.models import Candidate, Poll


logger = logging.getLogger(__name__)

CROSSED_BALLOT_CONFIG = 1
SNAPSHOT_METADATA_KEY = "danh_gia_gach_ten"
POSITIVE_LABEL = 1
NEGATIVE_LABEL = 0


def _log_dir():
    return Path(settings.BASE_DIR) / "runtime" / "logs" / "danh_gia_gach_ten"


def crossed_poll_log_path(poll_id):
    return _log_dir() / f"poll_{poll_id}.json"


def _ordered_candidates(poll):
    return list(Candidate.objects.filter(poll=poll).order_by("candidate_id"))


def _labels_from_selection(ballot, candidates):
    selected_ids = set(
        BallotSelection.objects.filter(ballot=ballot).values_list(
            "candidate_id",
            flat=True,
        )
    )

    labels = []
    rows = []
    for row_index, candidate in enumerate(candidates):
        label = 1 if candidate.candidate_id in selected_ids else 0
        labels.append(label)
        rows.append(
            {
                "row": row_index,
                "candidate_id": candidate.candidate_id,
                "label": label,
            }
        )

    return labels, rows


def _labels_from_submitted_votes(votes, candidates, original_selected_ids):
    vote_by_candidate_id = {
        int(vote.get("candidate_id")): bool(vote.get("voted", False))
        for vote in votes
        if vote.get("candidate_id") is not None
    }

    labels = []
    rows = []
    for row_index, candidate in enumerate(candidates):
        voted = vote_by_candidate_id.get(
            candidate.candidate_id,
            candidate.candidate_id in original_selected_ids,
        )
        label = 1 if voted else 0
        labels.append(label)
        rows.append(
            {
                "row": row_index,
                "candidate_id": candidate.candidate_id,
                "label": label,
            }
        )

    return labels, rows


def _model_label_from_ai_result(ai_result, row_index):
    cell_data = ai_result.get_cell_result(row_index, 0)
    if not cell_data:
        return None

    result_data = cell_data.get("result")
    if config_crossed.is_error_result(result_data):
        return None

    # Phieu gach ten: ten khong bi gach la lua chon "dong y".
    return NEGATIVE_LABEL if config_crossed.is_crossed_result(result_data) else POSITIVE_LABEL


def _empty_confusion_matrix():
    return {
        "true_positive": 0,
        "false_positive": 0,
        "false_negative": 0,
        "true_negative": 0,
        "unknown_model_label": 0,
    }


def _error_type(model_label, true_label):
    if model_label == POSITIVE_LABEL and true_label == NEGATIVE_LABEL:
        return "dong_y_sang_khong_dong_y"
    if model_label == NEGATIVE_LABEL and true_label == POSITIVE_LABEL:
        return "khong_dong_y_sang_dong_y"
    if model_label is None:
        return "khong_xac_dinh"
    return None


def _confusion_matrix(model_labels, true_labels):
    matrix = _empty_confusion_matrix()

    for index, true_label in enumerate(true_labels):
        model_label = model_labels[index] if index < len(model_labels) else None
        if model_label not in {NEGATIVE_LABEL, POSITIVE_LABEL}:
            matrix["unknown_model_label"] += 1
        elif model_label == POSITIVE_LABEL and true_label == POSITIVE_LABEL:
            matrix["true_positive"] += 1
        elif model_label == POSITIVE_LABEL and true_label == NEGATIVE_LABEL:
            matrix["false_positive"] += 1
        elif model_label == NEGATIVE_LABEL and true_label == POSITIVE_LABEL:
            matrix["false_negative"] += 1
        elif model_label == NEGATIVE_LABEL and true_label == NEGATIVE_LABEL:
            matrix["true_negative"] += 1

    return matrix


def _model_error_count(matrix):
    return matrix["false_positive"] + matrix["false_negative"]


def _error_breakdown(matrix):
    return {
        "tong": _model_error_count(matrix),
        "dong_y_sang_khong_dong_y": matrix["false_positive"],
        "khong_dong_y_sang_dong_y": matrix["false_negative"],
        "khong_xac_dinh": matrix["unknown_model_label"],
    }


def _add_confusion_matrix(total, increment):
    for key in total:
        total[key] += increment.get(key, 0)
    return total


def _fallback_model_labels(ballot, labels):
    ai_result = (
        AIModelResult.objects.filter(ballot=ballot)
        .order_by("-created_at")
        .first()
    )
    if not ai_result:
        return [None for _label in labels]

    return [
        _model_label_from_ai_result(ai_result, row_index)
        for row_index, _true_label in enumerate(labels)
    ]


def save_crossed_approval_snapshot(ballot, votes):
    """
    Save per-ballot data at approval time while the model selections are still
    available. This is specific to crossed-name ballots (config_number=1).
    """
    if not ballot.poll or ballot.poll.config_number != CROSSED_BALLOT_CONFIG:
        return False

    candidates = _ordered_candidates(ballot.poll)
    original_selected_ids = set(
        BallotSelection.objects.filter(ballot=ballot).values_list(
            "candidate_id",
            flat=True,
        )
    )
    true_labels, rows = _labels_from_submitted_votes(
        votes=votes,
        candidates=candidates,
        original_selected_ids=original_selected_ids,
    )

    model_labels = []
    for label_data in rows:
        candidate_id = label_data["candidate_id"]
        original_label = 1 if candidate_id in original_selected_ids else 0
        true_label = label_data["label"]
        model_labels.append(original_label)
        label_data["model_label"] = original_label
        label_data["true_label"] = true_label
        label_data["error_type"] = _error_type(original_label, true_label)

    matrix = _confusion_matrix(model_labels, true_labels)
    model_error_count = _model_error_count(matrix)

    ballot.refresh_from_db(fields=["metadata"])
    metadata = ballot.metadata if isinstance(ballot.metadata, dict) else {}
    metadata[SNAPSHOT_METADATA_KEY] = {
        "approved_at": timezone.now().isoformat(),
        "model_error_count": model_error_count,
        "model_labels": model_labels,
        "confusion_matrix": matrix,
        "error_breakdown": _error_breakdown(matrix),
        "total_rows": len(rows),
        "labels": true_labels,
        "rows": rows,
    }
    ballot.metadata = metadata
    ballot.save(update_fields=["metadata"])
    return True


def _snapshot_model_labels(ballot):
    if not ballot.metadata:
        return None

    snapshot = ballot.metadata.get(SNAPSHOT_METADATA_KEY)
    if not isinstance(snapshot, dict):
        return None

    model_labels = snapshot.get("model_labels")
    if not isinstance(model_labels, list):
        return None

    return model_labels


def build_crossed_poll_log_data(poll_id):
    poll = Poll.objects.get(poll_id=poll_id)
    if poll.config_number != CROSSED_BALLOT_CONFIG:
        return None

    candidates = _ordered_candidates(poll)
    approved_ballots = (
        Ballot.objects.filter(
            poll=poll,
            checking_status="DONE",
            counting_status="completed",
        )
        .order_by("ballot_id")
    )

    total_model_errors = 0
    total_matrix = _empty_confusion_matrix()
    total_rows = 0
    true_label_list = []

    for ballot in approved_ballots:
        labels, rows = _labels_from_selection(ballot, candidates)
        model_labels = _snapshot_model_labels(ballot)
        if not model_labels or len(model_labels) != len(labels):
            model_labels = _fallback_model_labels(ballot, labels)

        for index, row in enumerate(rows):
            model_label = model_labels[index] if index < len(model_labels) else None
            true_label = row["label"]
            row["model_label"] = model_label
            row["true_label"] = true_label
            row["error_type"] = _error_type(model_label, true_label)

        matrix = _confusion_matrix(model_labels, labels)
        error_count = _model_error_count(matrix)

        total_model_errors += error_count
        _add_confusion_matrix(total_matrix, matrix)
        total_rows += len(labels)
        true_label_list.append(
            {
                "ballot_id": ballot.ballot_id,
                "labels": labels,
                "model_labels": model_labels,
                "so_luong_loi_mo_hinh": error_count,
                "chi_tiet_loi_mo_hinh": _error_breakdown(matrix),
                "ma_tran_nham_lan": matrix,
                "rows": rows,
            }
        )

    return {
        "poll_id": poll.poll_id,
        "poll_title": poll.title,
        "config_number": poll.config_number,
        "updated_at": timezone.now().isoformat(),
        "so_luong_loi_mo_hinh": total_model_errors,
        "chi_tiet_loi_mo_hinh": _error_breakdown(total_matrix),
        "ma_tran_nham_lan": total_matrix,
        "nhan_duong": {
            "label": POSITIVE_LABEL,
            "name": "dong_y",
            "precision_formula": "true_positive / (true_positive + false_positive)",
            "recall_formula": "true_positive / (true_positive + false_negative)",
        },
        "tong_so_dong": total_rows,
        "tong_so_phieu": len(true_label_list),
        "danh_sach_nhan_dung": true_label_list,
    }


def write_crossed_poll_log(poll_id):
    data = build_crossed_poll_log_data(poll_id)
    if data is None:
        return None

    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = crossed_poll_log_path(poll_id)
    temp_path = log_path.with_name(f"{log_path.name}.{uuid.uuid4().hex}.tmp")

    with temp_path.open("w", encoding="utf-8") as log_file:
        json.dump(data, log_file, ensure_ascii=False, indent=2)
        log_file.write("\n")

    os.replace(temp_path, log_path)
    return log_path


def write_crossed_poll_log_safely(poll_id):
    try:
        return write_crossed_poll_log(poll_id)
    except Exception:
        logger.exception("Could not write crossed ballot evaluation log for poll %s", poll_id)
        return None
