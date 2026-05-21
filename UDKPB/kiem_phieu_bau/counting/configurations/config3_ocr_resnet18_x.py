from .base import (
    bulk_create_selections,
    clear_ballot_selections,
    evaluate_two_mark_columns,
    find_candidate_by_name,
    get_candidates,
    group_vote_table_rows,
    initialize_ai_result,
    has_x_mark,
    MODEL_RESNET18_X,
    MODEL_VIETNAMEOCR,
)


CONFIG_NUMBER = 3
START_ROW = 2 - 1
OCR_COL = 2 - 1
AGREE_COL = 3 - 1
DISAGREE_COL = 4 - 1


def apply(ai_result):
    rows, cols = initialize_ai_result(ai_result)

    if cols < 4:
        raise ValueError("Cau hinh 3 yeu cau bang 4 cot: STT, ten, dong y, khong dong y")

    for row in range(START_ROW, rows):
        ai_result.set_cell_model_config(row, OCR_COL, MODEL_VIETNAMEOCR)
        ai_result.set_cell_model_config(row, AGREE_COL, MODEL_RESNET18_X)
        ai_result.set_cell_model_config(row, DISAGREE_COL, MODEL_RESNET18_X)

    return ai_result


def evaluate_ballot_validity(ai_result):
    return evaluate_two_mark_columns(ai_result)


def create_ballot_selections(ballot, poll, ai_result):
    candidate_list, candidate_names = get_candidates(poll)
    clear_ballot_selections(ballot)

    selected_candidates = []
    rows_dict = group_vote_table_rows(ai_result)

    for row_data in rows_dict.values():
        mark_results = row_data['marks']
        ocr_result = row_data['ocr']
        mark_results.sort(key=lambda x: x[0])

        if not mark_results or not ocr_result:
            continue

        agree_result = next(
            (cell_data for col, cell_data in mark_results if col == AGREE_COL),
            None
        )
        disagree_result = next(
            (cell_data for col, cell_data in mark_results if col == DISAGREE_COL),
            None
        )
        if not agree_result:
            continue

        agree_data = agree_result.get('result', {})
        disagree_data = disagree_result.get('result', {}) if disagree_result else {}

        if not has_x_mark(agree_data) or has_x_mark(disagree_data):
            continue

        recognized_name = ocr_result.get('result', '').strip()
        if recognized_name.startswith("["):
            continue

        candidate = find_candidate_by_name(candidate_list, candidate_names, recognized_name)
        if candidate:
            selected_candidates.append(candidate)

    return bulk_create_selections(ballot, selected_candidates)
