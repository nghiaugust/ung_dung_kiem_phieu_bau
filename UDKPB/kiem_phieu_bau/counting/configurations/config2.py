from .base import (
    bulk_create_selections,
    clear_ballot_selections,
    evaluate_two_mark_columns,
    get_candidate_by_row,
    get_candidates,
    group_vote_table_rows,
    has_x_mark,
    initialize_ai_result,
    MODEL_YOLO_X,
)


CONFIG_NUMBER = 2


def apply(ai_result):
    rows, cols = initialize_ai_result(ai_result)

    yolo_col1 = 3 - 1
    yolo_col2 = 4 - 1
    start_row = 2 - 1

    for row in range(start_row, rows):
        ai_result.set_cell_model_config(row, yolo_col1, MODEL_YOLO_X)
        ai_result.set_cell_model_config(row, yolo_col2, MODEL_YOLO_X)

    return ai_result


def evaluate_ballot_validity(ai_result):
    return evaluate_two_mark_columns(ai_result)


def create_ballot_selections(ballot, poll, ai_result):
    candidate_list, _candidate_names = get_candidates(poll)
    clear_ballot_selections(ballot)

    selected_candidates = []
    start_row = 2 - 1
    rows_dict = group_vote_table_rows(ai_result)

    for row, row_data in rows_dict.items():
        yolo_results = row_data['yolo']
        yolo_results.sort(key=lambda x: x[0])

        if not yolo_results:
            continue

        agree_col, agree_result = yolo_results[0]
        result_data = agree_result.get('result', {})

        if not has_x_mark(result_data):
            continue

        candidate = get_candidate_by_row(candidate_list, row, start_row)
        if candidate:
            selected_candidates.append(candidate)

    return bulk_create_selections(ballot, selected_candidates)
