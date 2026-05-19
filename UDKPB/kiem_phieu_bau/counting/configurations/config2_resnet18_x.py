from .base import (
    bulk_create_selections,
    clear_ballot_selections,
    evaluate_two_mark_columns,
    get_candidate_by_row,
    get_candidates,
    group_vote_table_rows,
    has_x_mark,
    initialize_ai_result,
    MODEL_RESNET18_X,
)


CONFIG_NUMBER = 2
START_ROW = 2 - 1
AGREE_COL = 3 - 1
DISAGREE_COL = 4 - 1


def apply(ai_result):
    rows, cols = initialize_ai_result(ai_result)

    if cols < 4:
        raise ValueError("Cau hinh 2 yeu cau bang 4 cot: STT, ten, dong y, khong dong y")

    for row in range(START_ROW, rows):
        ai_result.set_cell_model_config(row, AGREE_COL, MODEL_RESNET18_X)
        ai_result.set_cell_model_config(row, DISAGREE_COL, MODEL_RESNET18_X)

    return ai_result


def evaluate_ballot_validity(ai_result):
    return evaluate_two_mark_columns(ai_result)


def create_ballot_selections(ballot, poll, ai_result):
    candidate_list, _candidate_names = get_candidates(poll)
    clear_ballot_selections(ballot)

    selected_candidates = []
    rows_dict = group_vote_table_rows(ai_result)

    for row, row_data in rows_dict.items():
        mark_results = row_data['marks']
        mark_results.sort(key=lambda x: x[0])

        if not mark_results:
            continue

        agree_result = next(
            (cell_data for col, cell_data in mark_results if col == AGREE_COL),
            None
        )
        if not agree_result:
            continue

        result_data = agree_result.get('result', {})

        if not has_x_mark(result_data):
            continue

        candidate = get_candidate_by_row(candidate_list, row, START_ROW)
        if candidate:
            selected_candidates.append(candidate)

    return bulk_create_selections(ballot, selected_candidates)
