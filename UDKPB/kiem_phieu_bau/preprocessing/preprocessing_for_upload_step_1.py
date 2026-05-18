"""
BƯỚC 1: LÀM PHẲNG ẢNH PHIẾU BẦU
Module xử lý làm phẳng ảnh phiếu bầu dựa trên ArUco markers và QR code
Được gọi khi upload phiếu từ mobile app

Yêu cầu:
- 1 QR code (góc trên trái) + 3 ArUco markers (3 góc còn lại)
- Ảnh đầu vào là ảnh chụp từ mobile
- Ảnh đầu ra là ảnh đã làm phẳng và chuẩn hóa kích thước
"""

import cv2
import numpy as np
import os
import gc

# Import detect_qr_codes từ ballot.doc_qr
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ballot.doc_qr import (
	SHARED_ARUCO_ID,
	detect_qr_codes,
	detect_shared_aruco_marker_corners,
	classify_shared_markers_from_corners,
)

# Import GPU utilities
from .gpu_utils import gpu_resize, gpu_warp_perspective, gpu_cvt_color, check_gpu_available


def phat_hien_qr_code(anh_mau, anh_xam=None):
	"""
	Phát hiện QR code bằng QReader (từ doc_qr.py)
	
	Args:
		anh_mau: Ảnh màu (BGR) - numpy array
		anh_xam: Ảnh grayscale (không sử dụng, chỉ để tương thích API)
	
	Returns:
		tuple: (qr_data, qr_corners) hoặc (None, None) nếu không tìm thấy
		- qr_data: str - Dữ liệu decode được
		- qr_corners: numpy array shape (4, 2) - 4 góc của QR code
	"""
	try:
		# Dùng detect_qr_codes từ doc_qr (QReader)
		qr_results = detect_qr_codes(anh_mau)
		
		if qr_results and len(qr_results) > 0:
			# Lấy QR code đầu tiên
			qr = qr_results[0]
			qr_data = qr.get('data')
			
			# Trích xuất corners từ polygon
			if 'polygon' in qr and qr['polygon']:
				# polygon là list[(x, y), ...]
				qr_corners = np.array(qr['polygon'], dtype=np.float32)
				return qr_data, qr_corners
			
			# Nếu không có polygon, tạo từ rect
			if 'rect' in qr:
				rect = qr['rect']
				left = rect['left']
				top = rect['top']
				right = left + rect['width']
				bottom = top + rect['height']
				
				# Tạo 4 góc: TL, TR, BR, BL
				qr_corners = np.array([
					[left, top],
					[right, top],
					[right, bottom],
					[left, bottom]
				], dtype=np.float32)
				
				return qr_data, qr_corners
	except Exception as e:
		print(f"[WARNING] QReader failed: {e}")
	
	return None, None


def _refine_qr_corners(gray_image, qr_corners):
	"""Refine QR corner candidates without failing the whole upload on OpenCV edge cases."""
	try:
		corners = np.array(qr_corners, dtype=np.float32).reshape(-1, 2)
	except Exception:
		return None

	if corners.shape[0] != 4:
		return None

	h, w = gray_image.shape[:2]
	corners[:, 0] = np.clip(corners[:, 0], 0, max(w - 1, 0))
	corners[:, 1] = np.clip(corners[:, 1], 0, max(h - 1, 0))

	try:
		criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
		refined = cv2.cornerSubPix(
			gray_image,
			corners.reshape(-1, 1, 2),
			winSize=(5, 5),
			zeroZone=(-1, -1),
			criteria=criteria
		)
		return refined.reshape(4, 2).astype(np.float32)
	except cv2.error as e:
		print(f"[STEP1 WARNING] Khong refine duoc QR corners, dung corners goc: {e}")
		return corners.astype(np.float32)


def _polygon_area(points):
	points = np.array(points, dtype=np.float32)
	x = points[:, 0]
	y = points[:, 1]
	return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _validate_warp_points(src_pts, rotation_label):
	"""Reject clearly crossed or degenerate marker geometry before perspective warp."""
	if src_pts.shape != (4, 2):
		return False

	if not np.all(np.isfinite(src_pts)):
		print(f"[STEP1 WARNING] ({rotation_label}) Toa do marker khong hop le")
		return False

	area = _polygon_area(src_pts)
	if area < 100:
		print(f"[STEP1 WARNING] ({rotation_label}) Vung marker qua nho hoac bi trung diem (area={area:.2f})")
		return False

	contour = src_pts.reshape(-1, 1, 2).astype(np.float32)
	if not cv2.isContourConvex(contour):
		print(f"[STEP1 WARNING] ({rotation_label}) Thu tu marker tao thanh polygon bi cheo, bo qua huong xoay nay")
		return False

	edge_lengths = [
		np.linalg.norm(src_pts[1] - src_pts[0]),
		np.linalg.norm(src_pts[2] - src_pts[1]),
		np.linalg.norm(src_pts[2] - src_pts[3]),
		np.linalg.norm(src_pts[3] - src_pts[0]),
	]
	if min(edge_lengths) < 10:
		print(f"[STEP1 WARNING] ({rotation_label}) Khoang cach marker qua nho: {edge_lengths}")
		return False

	return True


def _try_flatten_with_image(img, chieu_rong_pixel, chieu_dai_pixel, rotation_label):
	"""
	Thử làm phẳng trên 1 hướng ảnh cụ thể.
	Trả về (warped, qr_data) nếu thành công, ngược lại (None, None).
	"""
	h, w = img.shape[:2]
	# Chia ảnh làm 4 phần (từ tâm)
	mid_h, mid_w = h // 2, w // 2

	# Dictionary lưu góc markers theo id
	marker_corners = {}

	# Biến lưu data QR code
	qr_data_phat_hien = None
	qr_ref_point = None

	print(f"[STEP1] ({rotation_label}) Bắt đầu quét QR (Top-Left) + 3 ArUco dùng chung ID {SHARED_ARUCO_ID}...")

	# 1) Quét QR ở góc trên trái
	region = img[0:mid_h, 0:mid_w]
	gray_region = gpu_cvt_color(region, cv2.COLOR_BGR2GRAY)
	qr_data, qr_corners = phat_hien_qr_code(region, gray_region)

	qr_found = False
	if qr_data and qr_corners is not None:
		qr_corners = _refine_qr_corners(gray_region, qr_corners)
		if qr_corners is not None:
			qr_ref_point = np.mean(qr_corners, axis=0)
			br_idx = np.argmax(qr_corners[:, 0] + qr_corners[:, 1])
			marker_corners[0] = qr_corners[br_idx]
			qr_data_phat_hien = qr_data
			qr_found = True
			print(f"[STEP1] ({rotation_label}) Tìm thấy QR Code (ID 0) tại góc bottom-right: ({marker_corners[0][0]:.3f}, {marker_corners[0][1]:.3f})")

	if not qr_found:
		print(f"[STEP1] ({rotation_label}) Không tìm thấy QR ở độ phân giải gốc, thử upscale 3x...")
		new_w = int(region.shape[1] * 3.0)
		new_h = int(region.shape[0] * 3.0)
		region_upscaled = gpu_resize(region, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
		gray_region_upscaled = gpu_cvt_color(region_upscaled, cv2.COLOR_BGR2GRAY)
		qr_data, qr_corners = phat_hien_qr_code(region_upscaled, gray_region_upscaled)

		if qr_data and qr_corners is not None:
			qr_corners = _refine_qr_corners(gray_region_upscaled, qr_corners)
			if qr_corners is not None:
				qr_corners = qr_corners / 3.0
				qr_ref_point = np.mean(qr_corners, axis=0)
				br_idx = np.argmax(qr_corners[:, 0] + qr_corners[:, 1])
				marker_corners[0] = qr_corners[br_idx]
				qr_data_phat_hien = qr_data
				qr_found = True
				print(f"[STEP1] ({rotation_label}) Tìm thấy QR Code (ID 0) sau upscale 3x tại góc bottom-right: ({marker_corners[0][0]:.3f}, {marker_corners[0][1]:.3f})")

	if not qr_found:
		print(f"[STEP1] ({rotation_label}) Không tìm thấy QR sau upscale 3x, thử upscale 5x...")
		new_w = int(region.shape[1] * 5.0)
		new_h = int(region.shape[0] * 5.0)
		region_upscaled = gpu_resize(region, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
		gray_region_upscaled = gpu_cvt_color(region_upscaled, cv2.COLOR_BGR2GRAY)
		qr_data, qr_corners = phat_hien_qr_code(region_upscaled, gray_region_upscaled)

		if qr_data and qr_corners is not None:
			qr_corners = _refine_qr_corners(gray_region_upscaled, qr_corners)
			if qr_corners is not None:
				qr_corners = qr_corners / 5.0
				qr_ref_point = np.mean(qr_corners, axis=0)
				br_idx = np.argmax(qr_corners[:, 0] + qr_corners[:, 1])
				marker_corners[0] = qr_corners[br_idx]
				qr_data_phat_hien = qr_data
				qr_found = True
				print(f"[STEP1] ({rotation_label}) Tìm thấy QR Code (ID 0) sau upscale 5x tại góc bottom-right: ({marker_corners[0][0]:.3f}, {marker_corners[0][1]:.3f})")

	if not qr_found:
		print(f"[STEP1 WARNING] ({rotation_label}) Không tìm thấy QR Code trong vùng Top-Left (đã thử upscale 3x và 5x)")
		return None, None

	# 2) Quét toàn ảnh để lấy 3 marker ArUco cùng ID 17
	shared_markers_corners = detect_shared_aruco_marker_corners(
		img,
		shared_id=SHARED_ARUCO_ID,
		refine_subpixel=True,
	)

	if qr_ref_point is not None and 0 in marker_corners and len(shared_markers_corners) >= 3:
		phan_loai = classify_shared_markers_from_corners(shared_markers_corners, qr_ref_point)
		if phan_loai:
			marker_corners[1] = phan_loai[1]
			marker_corners[2] = phan_loai[2]
			marker_corners[3] = phan_loai[3]
			print(f"[STEP1] ({rotation_label}) Đã phân loại 3 marker ID {SHARED_ARUCO_ID} theo vị trí tương đối với QR")

	# Kiểm tra đủ 4 điểm (1 QR + 3 markers)
	if len(marker_corners) < 4:
		found_ids = sorted(marker_corners.keys())
		missing_ids = [i for i in range(4) if i not in marker_corners]
		print(f"[STEP1 WARNING] ({rotation_label}) Thiếu điểm tham chiếu: tìm thấy {found_ids}, thiếu {missing_ids}")
		return None, None

	print(f"[STEP1] ({rotation_label}) Tìm thấy đủ 4 điểm tham chiếu (QR + 3 marker ID {SHARED_ARUCO_ID}): {sorted(marker_corners.keys())}")

	# Tạo source points (góc markers trên ảnh gốc)
	src_pts = np.array([
		marker_corners[0],  # Top-Left
		marker_corners[1],  # Top-Right
		marker_corners[2],  # Bottom-Right
		marker_corners[3]   # Bottom-Left
	], dtype="float32")

	if not _validate_warp_points(src_pts, rotation_label):
		return None, None

	# Thêm padding cả 4 phía để không cắt vào nội dung
	padding = 50
	chieu_rong_pixel_with_padding = chieu_rong_pixel + 2 * padding
	chieu_dai_pixel_with_padding = chieu_dai_pixel + 2 * padding

	# Tạo destination points
	dst_pts = np.array([
		[padding, padding],                                          # Top-Left
		[chieu_rong_pixel + padding - 1, padding],                   # Top-Right
		[chieu_rong_pixel + padding - 1, chieu_dai_pixel + padding - 1], # Bottom-Right
		[padding, chieu_dai_pixel + padding - 1]                     # Bottom-Left
	], dtype="float32")

	# Biến đổi perspective (sử dụng GPU nếu có)
	M = cv2.getPerspectiveTransform(src_pts, dst_pts)
	warped = gpu_warp_perspective(img, M, (chieu_rong_pixel_with_padding, chieu_dai_pixel_with_padding))

	return warped, qr_data_phat_hien


def lam_phang_anh_phieu_bau(duong_dan_anh_dau_vao, duong_dan_anh_dau_ra, chieu_ngang_cm, chieu_doc_cm, dpi=300):
	"""
	Làm phẳng ảnh phiếu bầu dựa trên ArUco markers (yêu cầu đủ 4 markers)
	
	Quy trình:
	1. Chia ảnh và tìm QR code ở góc trên trái (ID 0) - lấy góc bottom-right
	2. Detect toàn ảnh các ArUco marker dùng chung ID 17
	3. Phân loại 3 marker thành top-right/bottom-right/bottom-left dựa vào vị trí tương đối với QR
	4. Áp dụng perspective transform để làm phẳng
	
	Args:
		duong_dan_anh_dau_vao: str - Đường dẫn tới ảnh đầu vào
		duong_dan_anh_dau_ra: str - Đường dẫn lưu ảnh đầu ra (đã làm phẳng)
		chieu_ngang_cm: float - Khoảng cách ngang giữa các markers (cm)
		chieu_doc_cm: float - Khoảng cách dọc giữa các markers (cm)
		dpi: int - DPI để chuyển đổi cm sang pixel (mặc định 300)
		
	Returns:
		tuple: (warped_image, qr_data)
			- warped_image: numpy.ndarray - Ảnh đã làm phẳng
			- qr_data: str | None - Dữ liệu từ QR code (hoặc None nếu không tìm thấy)
		
	Raises:
		ValueError: Nếu không tìm thấy đủ 4 markers hoặc không đọc được ảnh
		
	Note:
		- ID 0: QR Code (Top-Left) - Lấy góc bottom-right
		- 3 marker ArUco còn lại dùng chung ID 17
		- Vị trí Top-Right/Bottom-Right/Bottom-Left được phân loại theo vị trí tương đối với QR
		- Khoảng cách tính từ GÓC (không phải tâm)
		- DPI 300: 1 cm = 118.11 pixels
	"""
	# Chuyển đổi cm sang pixel
	# 1 inch = 2.54 cm, 1 inch = dpi pixels => 1 cm = dpi / 2.54 pixels
	pixels_per_cm = dpi / 2.54
	chieu_rong_pixel = int(chieu_ngang_cm * pixels_per_cm)
	chieu_dai_pixel = int(chieu_doc_cm * pixels_per_cm)
	
	# print(f"[STEP1] Chuyển đổi kích thước: {chieu_ngang_cm}cm x {chieu_doc_cm}cm -> {chieu_rong_pixel}px x {chieu_dai_pixel}px (DPI: {dpi})")
	
	# Đọc ảnh đầu vào
	img = cv2.imread(duong_dan_anh_dau_vao)
	if img is None:
		raise ValueError(f"Không thể đọc ảnh từ: {duong_dan_anh_dau_vao}")

	# print(f"[STEP1] Kích thước ảnh đầu vào: {w}x{h}")
	
	# In thông tin GPU (nếu có)
	if check_gpu_available():
		print(f"[STEP1] Sử dụng GPU acceleration cho xử lý ảnh")

	# Thử các hướng xoay để đưa QR về góc trên trái
	rotation_candidates = [
		("0", None),
		("90", cv2.ROTATE_90_CLOCKWISE),
		("180", cv2.ROTATE_180),
		("270", cv2.ROTATE_90_COUNTERCLOCKWISE),
	]

	warped = None
	qr_data_phat_hien = None
	used_rotation = None

	for rotation_label, rotation_code in rotation_candidates:
		if rotation_code is None:
			img_try = img
		else:
			print(f"[STEP1] Thử xoay ảnh {rotation_label} deg để đưa QR về góc trên trái...")
			img_try = cv2.rotate(img, rotation_code)

		warped, qr_data_phat_hien = _try_flatten_with_image(
			img_try,
			chieu_rong_pixel,
			chieu_dai_pixel,
			rotation_label
		)

		if rotation_code is not None:
			del img_try

		if warped is not None:
			used_rotation = rotation_label
			break

	if warped is None:
		# CLEANUP: Giải phóng memory của ảnh gốc
		del img
		gc.collect()
		raise ValueError("Không tìm thấy đủ 4 điểm tham chiếu ở bất kỳ hướng xoay nào")

	if used_rotation and used_rotation != "0":
		print(f"[STEP1] Đã xoay ảnh {used_rotation} deg trước khi làm phẳng")

	# Lưu ảnh đầu ra
	success = cv2.imwrite(duong_dan_anh_dau_ra, warped)
	if not success:
		raise ValueError(f"Không thể lưu ảnh tại: {duong_dan_anh_dau_ra}")

	# CLEANUP: Giải phóng memory của ảnh gốc (cực kỳ quan trọng!)
	# img có thể lên tới 35-50MB (4000x3000x3 bytes)
	del img
	gc.collect()

	# print(f"[STEP1] Đã lưu ảnh làm phẳng tại: {duong_dan_anh_dau_ra}")
	print(f"[STEP1] ========== HOÀN THÀNH BƯỚC 1: LÀM PHẲNG ẢNH ==========")

	return warped, qr_data_phat_hien
