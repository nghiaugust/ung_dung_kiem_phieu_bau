from .base import (
    bulk_create_selections,
    clear_ballot_selections,
    evaluate_two_mark_columns,
    find_candidate_by_name,
    get_candidates,
    group_vote_table_rows,
    initialize_ai_result,
    has_x_mark,
    MODEL_VIETNAMEOCR,
    MODEL_YOLO_X,
)


CONFIG_NUMBER = 1


def apply(ai_result):
    rows, cols = initialize_ai_result(ai_result)

    ocr_col = 2 - 1
    yolo_col1 = 3 - 1
    yolo_col2 = 4 - 1
    start_row = 2 - 1

    for row in range(start_row, rows):
        ai_result.set_cell_model_config(row, ocr_col, MODEL_VIETNAMEOCR)
        ai_result.set_cell_model_config(row, yolo_col1, MODEL_YOLO_X)
        ai_result.set_cell_model_config(row, yolo_col2, MODEL_YOLO_X)

    return ai_result


def evaluate_ballot_validity(ai_result):
    return evaluate_two_mark_columns(ai_result)


def create_ballot_selections(ballot, poll, ai_result):
    candidate_list, candidate_names = get_candidates(poll)
    clear_ballot_selections(ballot)

    selected_candidates = []
    rows_dict = group_vote_table_rows(ai_result)

    for row_data in rows_dict.values():
        yolo_results = row_data['yolo']
        ocr_result = row_data['ocr']
        yolo_results.sort(key=lambda x: x[0])

        if not yolo_results or not ocr_result:
            continue

        agree_col, agree_result = yolo_results[0]
        result_data = agree_result.get('result', {})

        if not has_x_mark(result_data):
            continue

        recognized_name = ocr_result.get('result', '').strip()
        if recognized_name.startswith("["):
            continue

        candidate = find_candidate_by_name(candidate_list, candidate_names, recognized_name)
        if candidate:
            selected_candidates.append(candidate)

    return bulk_create_selections(ballot, selected_candidates)
