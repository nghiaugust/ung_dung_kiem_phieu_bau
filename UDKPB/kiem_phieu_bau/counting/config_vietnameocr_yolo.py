"""
Config 2: VietNameOCR + YOLO.

VietNameOCR reads the candidate name column and YOLO detects vote marks.
"""


CONFIG_NUMBER = 2
CONFIG_NAME = "VietNameOCR + YOLO"
REQUIRED_SERVICES = {"vietnameocr", "yolo"}


def apply(ai_result):
	ai_result.initialize_config()

	rows, cols = ai_result.get_table_dimensions()
	if rows is None or cols is None:
		raise ValueError("Không thể lấy table dimensions từ BallotDocument")

	vietnameocr_col = 2 - 1
	yolo_col1 = 3 - 1
	yolo_col2 = 4 - 1
	start_row = 2 - 1

	for row in range(start_row, rows):
		ai_result.set_cell_model_config(row, vietnameocr_col, "vietnameocr")
		ai_result.set_cell_model_config(row, yolo_col1, "yolo")
		ai_result.set_cell_model_config(row, yolo_col2, "yolo")

	return ai_result
