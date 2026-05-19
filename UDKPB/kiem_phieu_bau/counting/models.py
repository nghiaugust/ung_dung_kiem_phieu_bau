from django.db import models
from ballot.models import Ballot
from form.models import BallotDocument


class AIModelResult(models.Model):
	"""
	Model lưu kết quả AI cho từng phiếu bầu
	
	Cấu trúc config_model JSON (cấu hình ô nào dùng model nào):
	{
		"table_dimensions": {
			"rows": 3,
			"cols": 4
		},
		"cell_models": {
			"0_0": "model_vietnameocr",
			"0_1": "model_yolo_x",
			"1_0": "model_vietnameocr",
			"1_1": "model_yolo_x"
		}
	}
	
	Cấu trúc result_model JSON (chỉ lưu kết quả):
	{
		"cells": {
			"0_0": {
				"result": "Nguyễn Văn A",
				"confidence": 0.95
			},
			"0_1": {
				"result": {"class": "checkbox", "checked": true},
				"confidence": 0.89
			}
		}
	}
	"""
	
	result_id = models.AutoField(primary_key=True)
	ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name='ai_results')
	
	# Cấu hình model cho từng ô
	config_model = models.JSONField(default=dict, help_text='Cấu hình ô nào dùng model nào')
	
	# Kết quả từ model (chỉ chứa results, không chứa tên model)
	result_model = models.JSONField(default=dict, help_text='Kết quả detect của từng ô')
	
	# Metadata
	created_at = models.DateTimeField(auto_now_add=True)
	processing_time = models.FloatField(null=True, blank=True, help_text='Thời gian xử lý (giây)')
	
	# Trạng thái
	status = models.CharField(max_length=20, default='success', choices=[
		('success', 'Thành công'),
		('failed', 'Thất bại'),
		('partial', 'Một phần thành công'),
	])
	error_message = models.TextField(null=True, blank=True)
	
	class Meta:
		db_table = 'ai_model_result'
		verbose_name = 'Kết quả AI Model'
		verbose_name_plural = 'Kết quả AI Models'
		indexes = [
			models.Index(fields=['ballot']),
			models.Index(fields=['created_at']),
		]
	
	def __str__(self):
		return f"AIResult - Ballot {self.ballot_id} - {self.status}"
	
	def initialize_config(self):
		"""
		Khởi tạo cấu trúc config_model với table dimensions từ BallotDocument
		Cần gọi hàm này trước khi set_cell_model_config
		"""
		# Lấy số hàng, cột từ BallotDocument (giống cách lấy ở step_2)
		try:
			ballot_doc = BallotDocument.objects.filter(
				poll=self.ballot.poll
			).order_by('-created_at').first()
			
			if ballot_doc:
				num_rows, num_cols = ballot_doc.get_first_table_dimensions()
				
				if num_rows is not None and num_cols is not None:
					rows, cols = num_rows, num_cols
				else:
					# Fallback mặc định
					rows, cols = 3, 4
			else:
				# Fallback mặc định
				rows, cols = 3, 4
		except Exception as e:
			print(f"[AIModelResult] Lỗi khi lấy table dimensions: {e}")
			rows, cols = 3, 4
		
		# Khởi tạo cấu trúc config_model
		self.config_model = {
			"table_dimensions": {
				"rows": rows,
				"cols": cols
			},
			"cell_models": {}
		}
		
		# Khởi tạo cấu trúc result_model
		self.result_model = {
			"cells": {}
		}
		
		self.save()
	
	def set_cell_model_config(self, row, col, model_name):
		"""
		Cấu hình ô nào sử dụng model nào
		
		Args:
			row: int - Số hàng (0-indexed)
			col: int - Số cột (0-indexed)
			model_name: str - Ten model ('model_vietnameocr', 'model_yolo_x', etc.)
		"""
		cell_key = f"{row}_{col}"
		
		if "cell_models" not in self.config_model:
			self.config_model["cell_models"] = {}
		
		self.config_model["cell_models"][cell_key] = model_name
		self.save()
	
	def get_cell_model(self, row, col):
		"""
		Lấy tên model được cấu hình cho ô cụ thể
		
		Args:
			row: int - Số hàng (0-indexed)
			col: int - Số cột (0-indexed)
			
		Returns:
			str hoac None: Ten model ('model_vietnameocr', 'model_yolo_x', etc.)
		"""
		cell_key = f"{row}_{col}"
		return self.config_model.get("cell_models", {}).get(cell_key)
	
	def set_cell_result(self, row, col, result, confidence=None):
		"""
		Lưu kết quả detect cho một ô cụ thể
		
		Args:
			row: int - Số hàng (0-indexed)
			col: int - Số cột (0-indexed)
			result: any - Kết quả detect (text, dict, etc.)
			confidence: float - Độ tin cậy (nếu có)
		"""
		cell_key = f"{row}_{col}"
		
		cell_data = {
			"result": result
		}
		
		if confidence is not None:
			cell_data["confidence"] = confidence
		
		if "cells" not in self.result_model:
			self.result_model["cells"] = {}
		
		self.result_model["cells"][cell_key] = cell_data
		self.save()
	
	def get_cell_result(self, row, col):
		"""
		Lấy kết quả của một ô cụ thể
		
		Args:
			row: int - Số hàng (0-indexed)
			col: int - Số cột (0-indexed)
			
		Returns:
			dict hoặc None: {'result': ..., 'confidence': ...}
		"""
		cell_key = f"{row}_{col}"
		return self.result_model.get("cells", {}).get(cell_key)
	
	def get_cell_info(self, row, col):
		"""
		Lấy đầy đủ thông tin của một ô (model + result)
		
		Args:
			row: int - Số hàng (0-indexed)
			col: int - Số cột (0-indexed)
			
		Returns:
			dict: {
				'model': str,
				'result': any,
				'confidence': float (nếu có)
			}
		"""
		model_name = self.get_cell_model(row, col)
		result_data = self.get_cell_result(row, col)
		
		if model_name is None or result_data is None:
			return None
		
		info = {
			'model': model_name,
			'result': result_data.get('result')
		}
		
		if 'confidence' in result_data:
			info['confidence'] = result_data['confidence']
		
		return info
	
	def get_table_dimensions(self):
		"""
		Lấy kích thước bảng
		
		Returns:
			tuple: (rows, cols)
		"""
		dims = self.config_model.get("table_dimensions", {})
		return dims.get("rows"), dims.get("cols")
	
	def get_all_cell_models(self):
		"""
		Lấy cấu hình model của tất cả các ô
		
		Returns:
			dict: {cell_key: model_name}
		"""
		return self.config_model.get("cell_models", {})
	
	def get_all_cell_results(self):
		"""
		Lấy kết quả của tất cả các ô
		
		Returns:
			dict: {cell_key: {'result': ..., 'confidence': ...}}
		"""
		return self.result_model.get("cells", {})
	
	def get_all_cells_info(self):
		"""
		Lấy đầy đủ thông tin của tất cả các ô (model + result)
		
		Returns:
			dict: {
				cell_key: {
					'model': str,
					'result': any,
					'confidence': float (nếu có)
				}
			}
		"""
		cell_models = self.get_all_cell_models()
		cell_results = self.get_all_cell_results()
		
		all_info = {}
		for cell_key in cell_models.keys():
			if cell_key in cell_results:
				all_info[cell_key] = {
					'model': cell_models[cell_key],
					'result': cell_results[cell_key].get('result')
				}
				if 'confidence' in cell_results[cell_key]:
					all_info[cell_key]['confidence'] = cell_results[cell_key]['confidence']
		
		return all_info
	
	def get_cells_by_model(self, model_name):
		"""
		Lấy tất cả ô được cấu hình cho một model cụ thể
		
		Args:
			model_name: str - Tên model
			
		Returns:
			dict: {cell_key: {'result': ..., 'confidence': ...}}
		"""
		cell_models = self.get_all_cell_models()
		cell_results = self.get_all_cell_results()
		
		filtered = {}
		for cell_key, configured_model in cell_models.items():
			if configured_model == model_name and cell_key in cell_results:
				filtered[cell_key] = cell_results[cell_key]
		
		return filtered
