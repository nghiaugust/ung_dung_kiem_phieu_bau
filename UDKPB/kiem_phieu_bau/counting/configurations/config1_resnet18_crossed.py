from .base import (
    bulk_create_selections,
    clear_ballot_selections,
    get_candidate_by_row,
    get_candidates,
    initialize_ai_result,
    MODEL_RESNET18_CROSSED,
)


CONFIG_NUMBER = 1
MODEL_NAME = MODEL_RESNET18_CROSSED
START_ROW = 0
NAME_COL = 0
STRUCK_LABELS = {'struck', 'gach_ten', 'crossed_out', 'name_struck'}
NOT_STRUCK_LABELS = {'not_struck', 'khong_gach_ten', 'clear', 'normal'}


def apply(ai_result):
    rows, cols = initialize_ai_result(ai_result)

    if cols < 1:
        raise ValueError("Cau hinh 1 yeu cau bang toi thieu 1 cot")

    for row in range(START_ROW, rows):
        ai_result.set_cell_model_config(row, NAME_COL, MODEL_NAME)

    return ai_result


def _is_struck(result_data):
    if not isinstance(result_data, dict):
        return False

    is_struck = result_data.get('is_struck')
    if isinstance(is_struck, bool):
        return is_struck

    label = str(result_data.get('label', '')).lower()
    return label in STRUCK_LABELS


def _has_strike_decision(result_data):
    if not isinstance(result_data, dict):
        return False

    if isinstance(result_data.get('is_struck'), bool):
        return True

    label = str(result_data.get('label', '')).lower()
    return label in STRUCK_LABELS or label in NOT_STRUCK_LABELS


def _is_error_result(result_data):
    if isinstance(result_data, str):
        return result_data.startswith("[")
    if isinstance(result_data, dict):
        return bool(result_data.get('error')) or not _has_strike_decision(result_data)
    return result_data is None


def evaluate_ballot_validity(ai_result):
    cell_models = ai_result.get_all_cell_models()
    cell_results = ai_result.get_all_cell_results()

    configured_cells = [
        cell_key
        for cell_key, model_name in cell_models.items()
        if model_name == MODEL_NAME
    ]

    if not configured_cells:
        return False

    for cell_key in configured_cells:
        cell_data = cell_results.get(cell_key)
        if not cell_data or _is_error_result(cell_data.get('result')):
            return False

    return True


def create_ballot_selections(ballot, poll, ai_result):
    candidate_list, _candidate_names = get_candidates(poll)
    clear_ballot_selections(ballot)

    selected_candidates = []
    resnet18_crossed_cells = ai_result.get_cells_by_model(MODEL_NAME)

    for cell_key, cell_data in sorted(
        resnet18_crossed_cells.items(),
        key=lambda item: tuple(map(int, item[0].split('_')))
    ):
        row, col = map(int, cell_key.split('_'))
        if col != NAME_COL:
            continue

        result_data = cell_data.get('result')
        if _is_error_result(result_data):
            continue

        # Phieu gach ten: ung vien khong bi gach la ung vien duoc chon.
        if _is_struck(result_data):
            continue

        candidate = get_candidate_by_row(candidate_list, row, START_ROW)
        if candidate:
            selected_candidates.append(candidate)

    return bulk_create_selections(ballot, selected_candidates)
