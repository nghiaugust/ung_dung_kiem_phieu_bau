"""
Module quản lý cấu hình model cho AIModelResult
Cung cấp các hàm để khởi tạo config_model cho từng loại cấu hình
"""


def apply_config1(ai_result):
	"""
	Áp dụng Cấu hình 1: TrOCR nhận diện tên + YOLO detect dấu X
	
	Cấu hình:
	- TrOCR: Nhận diện tên (cột 2, từ dòng 2 trở đi)
	- YOLO: Detect dấu X (cột 3 và 4, từ dòng 2 trở đi)
	
	Args:
		ai_result: AIModelResult object - Đã được tạo với ballot
		
	Returns:
		AIModelResult: Object đã được cấu hình
	"""
	# Khởi tạo config (lấy rows, cols từ BallotDocument)
	ai_result.initialize_config()
	
	# Lấy số hàng, cột
	rows, cols = ai_result.get_table_dimensions()
	
	if rows is None or cols is None:
		raise ValueError("Không thể lấy table dimensions từ BallotDocument")
	
	# Cấu hình index (UI tính từ 1, database tính từ 0)
	trocr_col = 2 - 1  # Cột 2 → index 1
	yolo_col1 = 3 - 1  # Cột 3 → index 2
	yolo_col2 = 4 - 1  # Cột 4 → index 3
	start_row = 2 - 1  # Dòng 2 → index 1
	
	# Cấu hình từng ô
	for row in range(start_row, rows):
		# TrOCR cho cột tên (cột 2)
		ai_result.set_cell_model_config(row, trocr_col, 'trocr')
		
		# YOLO cho cột 3 và 4
		ai_result.set_cell_model_config(row, yolo_col1, 'yolo')
		ai_result.set_cell_model_config(row, yolo_col2, 'yolo')
	
	# print(f"[CONFIG1] Đã cấu hình {rows - start_row} dòng x 3 cột (1 TrOCR + 2 YOLO)")
	
	return ai_result


def apply_config2(ai_result):
	"""
	Áp dụng Cấu hình 2: Tên theo thứ tự danh sách ứng viên + YOLO detect dấu X
	
	Cấu hình:
	- Tên lấy theo thứ tự danh sách ứng viên (không dùng TrOCR)
	- YOLO: Detect dấu X (cột 3 và 4, từ dòng 2 trở đi)
	
	Args:
		ai_result: AIModelResult object - Đã được tạo với ballot
		
	Returns:
		AIModelResult: Object đã được cấu hình
	"""
	# Khởi tạo config (lấy rows, cols từ BallotDocument)
	ai_result.initialize_config()
	
	# Lấy số hàng, cột
	rows, cols = ai_result.get_table_dimensions()
	
	if rows is None or cols is None:
		raise ValueError("Không thể lấy table dimensions từ BallotDocument")
	
	# Cấu hình index (UI tính từ 1, database tính từ 0)
	yolo_col1 = 3 - 1  # Cột 3 → index 2
	yolo_col2 = 4 - 1  # Cột 4 → index 3
	start_row = 2 - 1  # Dòng 2 → index 1
	
	# Cấu hình từng ô
	for row in range(start_row, rows):
		# Chỉ YOLO cho cột 3 và 4 (không có TrOCR)
		ai_result.set_cell_model_config(row, yolo_col1, 'yolo')
		ai_result.set_cell_model_config(row, yolo_col2, 'yolo')
	
	# print(f"[CONFIG2] Đã cấu hình {rows - start_row} dòng x 2 cột (chỉ YOLO, không TrOCR)")
	
	return ai_result


def get_config_summary(ai_result):
	"""
	Lấy tóm tắt cấu hình của AIModelResult
	
	Args:
		ai_result: AIModelResult object
		
	Returns:
		dict: {
			'rows': int,
			'cols': int,
			'trocr_cells': list,
			'yolo_cells': list,
			'total_configured': int
		}
	"""
	rows, cols = ai_result.get_table_dimensions()
	all_models = ai_result.get_all_cell_models()
	
	trocr_cells = []
	yolo_cells = []
	
	for cell_key, model_name in all_models.items():
		if model_name == 'trocr':
			trocr_cells.append(cell_key)
		elif model_name == 'yolo':
			yolo_cells.append(cell_key)
	
	return {
		'rows': rows,
		'cols': cols,
		'trocr_cells': trocr_cells,
		'yolo_cells': yolo_cells,
		'total_configured': len(all_models)
	}
