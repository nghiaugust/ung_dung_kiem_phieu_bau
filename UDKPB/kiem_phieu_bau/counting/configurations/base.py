import difflib

from ballot.models import BallotSelection
from poll.models import Candidate


MODEL_VIETNAMEOCR = 'model_vietnameocr'
MODEL_YOLO_X = 'model_yolo_x'
MODEL_RESNET18_CROSSED = 'model_resnet18_crossed'


CONFIG_DEFINITIONS = {
    1: {
        'label': 'Cau hinh 1: VietNameOCR + YOLO-X',
        'description': 'VietNameOCR nhan dien ten, YOLO-X detect dau X o cot Dong y/Khong dong y',
        'required_services': [MODEL_VIETNAMEOCR, MODEL_YOLO_X],
    },
    2: {
        'label': 'Cau hinh 2: Theo thu tu + YOLO-X',
        'description': 'Ten theo thu tu danh sach ung vien, YOLO-X detect dau X',
        'required_services': [MODEL_YOLO_X],
    },
    3: {
        'label': 'Cau hinh 3: Phieu gach ten',
        'description': 'model_resnet18_crossed detect ung vien bi gach ten trong bang 1 cot',
        'required_services': [MODEL_RESNET18_CROSSED],
    },
}


def initialize_ai_result(ai_result):
    ai_result.initialize_config()
    rows, cols = ai_result.get_table_dimensions()
    if rows is None or cols is None:
        raise ValueError("Khong the lay table dimensions tu BallotDocument")
    return rows, cols


def has_x_mark(result_data):
    if isinstance(result_data, dict):
        label = result_data.get('label', '')
    else:
        label = str(result_data) if result_data is not None else ''
    return 'x_mark' in str(label).lower()


def get_candidates(poll):
    candidate_list = list(Candidate.objects.filter(poll=poll).order_by('candidate_id'))
    candidate_names = {c.candidate_id: c.name for c in candidate_list}
    return candidate_list, candidate_names


def find_candidate_by_name(candidate_list, candidate_names, recognized_name, min_ratio=0.6):
    if not recognized_name:
        return None

    best_match_id = None
    best_match_ratio = 0.0

    for candidate_id, candidate_name in candidate_names.items():
        ratio = difflib.SequenceMatcher(
            None,
            recognized_name.upper(),
            candidate_name.upper()
        ).ratio()

        if ratio > best_match_ratio:
            best_match_ratio = ratio
            best_match_id = candidate_id

    if best_match_id and best_match_ratio >= min_ratio:
        return next(
            (c for c in candidate_list if c.candidate_id == best_match_id),
            None
        )

    return None


def get_candidate_by_row(candidate_list, row, start_row):
    candidate_index = row - start_row
    if 0 <= candidate_index < len(candidate_list):
        return candidate_list[candidate_index]
    return None


def clear_ballot_selections(ballot):
    BallotSelection.objects.filter(ballot=ballot).delete()


def bulk_create_selections(ballot, candidates):
    selections = [
        BallotSelection(ballot=ballot, candidate_id=candidate.candidate_id)
        for candidate in candidates
        if candidate is not None
    ]

    if selections:
        BallotSelection.objects.bulk_create(selections)

    return len(selections)


def group_vote_table_rows(ai_result):
    yolo_cells = ai_result.get_cells_by_model(MODEL_YOLO_X)
    ocr_cells = ai_result.get_cells_by_model(MODEL_VIETNAMEOCR)

    rows_dict = {}
    for cell_key, cell_data in yolo_cells.items():
        row, col = map(int, cell_key.split('_'))
        if row not in rows_dict:
            rows_dict[row] = {'yolo': [], 'ocr': None}
        rows_dict[row]['yolo'].append((col, cell_data))

    for cell_key, cell_data in ocr_cells.items():
        row, col = map(int, cell_key.split('_'))
        if row not in rows_dict:
            rows_dict[row] = {'yolo': [], 'ocr': None}
        rows_dict[row]['ocr'] = cell_data

    return rows_dict


def evaluate_two_mark_columns(ai_result):
    cell_models = ai_result.get_all_cell_models()
    cell_results = ai_result.get_all_cell_results()

    rows = {}
    for cell_key, model_name in cell_models.items():
        if model_name != MODEL_YOLO_X:
            continue
        try:
            row, col = map(int, cell_key.split('_'))
        except ValueError:
            continue
        if row not in rows:
            rows[row] = {}
        rows[row][col] = cell_results.get(cell_key, {}).get('result')

    if not rows:
        return True

    for col_results in rows.values():
        mark_count = 0
        for result in col_results.values():
            if has_x_mark(result):
                mark_count += 1
        if mark_count == 0 or mark_count > 1:
            return False

    return True
