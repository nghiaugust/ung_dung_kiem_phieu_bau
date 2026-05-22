"""
Config 1: only YOLO.

Candidate names are resolved by row order, so this config only sends the
agree/disagree cells to YOLO.
"""


CONFIG_NUMBER = 1
CONFIG_NAME = "Chỉ YOLO"
REQUIRED_SERVICES = {"yolo"}


def apply(ai_result):
	ai_result.initialize_config()

	rows, cols = ai_result.get_table_dimensions()
	if rows is None or cols is None:
		raise ValueError("Không thể lấy table dimensions từ BallotDocument")

	yolo_col1 = 3 - 1
	yolo_col2 = 4 - 1
	start_row = 2 - 1

	for row in range(start_row, rows):
		ai_result.set_cell_model_config(row, yolo_col1, "yolo")
		ai_result.set_cell_model_config(row, yolo_col2, "yolo")

	return ai_result
