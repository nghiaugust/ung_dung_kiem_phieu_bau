"""
Dispatcher for counting model configurations.

Config 1: only YOLO.
Config 2: VietNameOCR + YOLO.
"""
from . import config_vietnameocr_yolo, config_yolo_only


CONFIGS = {
	1: config_yolo_only,
	2: config_vietnameocr_yolo,
}


def apply_config(ai_result, config_number):
	config = CONFIGS.get(config_number)
	if config is None:
		raise ValueError(f"Cấu hình không hợp lệ: {config_number}")
	return config.apply(ai_result)


def apply_config1(ai_result):
	return apply_config(ai_result, 1)


def apply_config2(ai_result):
	return apply_config(ai_result, 2)


def get_required_services(config_number):
	config = CONFIGS.get(config_number)
	if config is None:
		return set()
	return set(config.REQUIRED_SERVICES)


def is_config_ready(config_number, *, yolo_status=False, vietnameocr_status=False):
	required_services = get_required_services(config_number)
	if not required_services:
		return False

	service_status = {
		"yolo": yolo_status,
		"vietnameocr": vietnameocr_status,
	}

	return all(service_status.get(service, False) for service in required_services)


def get_config_summary(ai_result):
	rows, cols = ai_result.get_table_dimensions()
	all_models = ai_result.get_all_cell_models()

	vietnameocr_cells = []
	yolo_cells = []

	for cell_key, model_name in all_models.items():
		if model_name == "vietnameocr":
			vietnameocr_cells.append(cell_key)
		elif model_name == "yolo":
			yolo_cells.append(cell_key)

	return {
		"rows": rows,
		"cols": cols,
		"vietnameocr_cells": vietnameocr_cells,
		"yolo_cells": yolo_cells,
		"total_configured": len(all_models),
	}
