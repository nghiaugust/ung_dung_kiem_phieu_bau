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


def _chon_goc_gan_tam_nhat(marker_corners, tam_phieu):
	"""Chọn corner của marker gần tâm phiếu nhất (góc phía trong)."""
	corners = np.asarray(marker_corners, dtype=np.float32)
	tam = np.asarray(tam_phieu, dtype=np.float32)
	distances = np.linalg.norm(corners - tam, axis=1)
	return corners[int(np.argmin(distances))]


def _phan_loai_3_marker_theo_vi_tri(shared_markers_corners, qr_ref_point):
	"""
	Phân loại 3 marker dùng chung ID thành top-right/bottom-right/bottom-left.
	Ưu tiên marker lớn để giảm nhiễu detect sai.
	"""
	if len(shared_markers_corners) < 3:
		return None

	qr_x, qr_y = float(qr_ref_point[0]), float(qr_ref_point[1])
	marker_meta_all = []
	for corners in shared_markers_corners:
		arr = np.asarray(corners, dtype=np.float32)
		marker_meta_all.append({
			'corners': arr,
			'center_x': float(np.mean(arr[:, 0])),
			'center_y': float(np.mean(arr[:, 1])),
			'area': abs(float(cv2.contourArea(arr)))
		})

	max_area = max(m['area'] for m in marker_meta_all)
	area_threshold = max_area * 0.35
	marker_meta = [m for m in marker_meta_all if m['area'] >= area_threshold]

	# Nếu lọc theo diện tích vẫn thiếu marker thì lấy 3 marker lớn nhất.
	if len(marker_meta) < 3:
		marker_meta = sorted(marker_meta_all, key=lambda m: m['area'], reverse=True)[:3]

	right_side = [m for m in marker_meta if m['center_x'] > qr_x]
	if len(right_side) >= 2:
		top_right = min(right_side, key=lambda m: m['center_y'])
		remaining_for_br = [m for m in marker_meta if m is not top_right]
		bottom_right = max(remaining_for_br, key=lambda m: (m['center_x'], m['center_y']))
	else:
		# Fallback khi detect thiếu marker ở bên phải: chọn theo score hình học.
		top_right = max(marker_meta, key=lambda m: (m['center_x'] - 0.6 * abs(m['center_y'] - qr_y)))
		remaining_for_br = [m for m in marker_meta if m is not top_right]
		if len(remaining_for_br) < 2:
			return None
		bottom_right = max(remaining_for_br, key=lambda m: (m['center_x'] + m['center_y']))

	remaining = [m for m in marker_meta if m is not top_right and m is not bottom_right]
	if not remaining:
		return None

	below_qr = [m for m in remaining if m['center_y'] > qr_y]
	if below_qr:
		bottom_left = min(below_qr, key=lambda m: m['center_x'])
	else:
		bottom_left = max(remaining, key=lambda m: m['center_y'])

	return {
		'top_right': top_right,
		'bottom_right': bottom_right,
		'bottom_left': bottom_left,
	}


def _validate_src_points(src_pts, image_shape):
	"""Kiểm tra 4 điểm phối cảnh để tránh warp sai gây ảnh đen/bóp méo."""
	pts = np.asarray(src_pts, dtype=np.float32)
	if pts.shape != (4, 2):
		return False, 'src_pts phải có shape (4,2)'

	if not np.isfinite(pts).all():
		return False, 'src_pts chứa giá trị không hợp lệ (NaN/Inf)'

	h, w = image_shape[:2]
	img_area = float(w * h)
	quad_area = abs(float(cv2.contourArea(pts)))
	if quad_area < img_area * 0.01:
		return False, f'diện tích tứ giác quá nhỏ ({quad_area:.1f}px)'

	bbox_w = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
	bbox_h = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))
	if bbox_w < w * 0.15 or bbox_h < h * 0.15:
		return False, f'bbox điểm tham chiếu quá nhỏ ({bbox_w:.1f}x{bbox_h:.1f})'

	if not cv2.isContourConvex(pts.astype(np.float32).reshape(-1, 1, 2)):
		return False, '4 điểm không tạo thành tứ giác lồi'

	edge_lengths = [
		float(np.linalg.norm(pts[i] - pts[(i + 1) % 4]))
		for i in range(4)
	]
	if min(edge_lengths) < 20.0:
		return False, f'cạnh quá ngắn ({min(edge_lengths):.1f}px)'

	return True, None


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
	
	h, w = img.shape[:2]
	# print(f"[STEP1] Kích thước ảnh đầu vào: {w}x{h}")
	
	# In thông tin GPU (nếu có)
	if check_gpu_available():
		print(f"[STEP1] Sử dụng GPU acceleration cho xử lý ảnh")
	
	# Chia ảnh làm 4 phần (từ tâm)
	mid_h, mid_w = h // 2, w // 2
	
	# Dictionary lưu góc markers theo id
	marker_corners = {}
	qr_corners_full = None
	qr_ref_point = None
	
	# Biến lưu data QR code
	qr_data_phat_hien = None
	
	print(f"[STEP1] Bắt đầu quét QR (Top-Left) + 3 ArUco dùng chung ID {SHARED_ARUCO_ID}...")

	# 1) Quét QR ở góc trên trái
	region = img[0:mid_h, 0:mid_w]
	gray_region = gpu_cvt_color(region, cv2.COLOR_BGR2GRAY)
	qr_data, qr_corners = phat_hien_qr_code(region, gray_region)

	qr_found = False
	if qr_data and qr_corners is not None:
		criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
		corners_refined = cv2.cornerSubPix(
			gray_region,
			qr_corners.reshape(-1, 1, 2),
			winSize=(5, 5),
			zeroZone=(-1, -1),
			criteria=criteria
		)
		qr_corners = corners_refined.reshape(4, 2).astype(np.float32)
		qr_corners_full = qr_corners
		qr_ref_point = np.mean(qr_corners_full, axis=0)
		br_idx = np.argmax(qr_corners[:, 0] + qr_corners[:, 1])
		marker_corners[0] = qr_corners[br_idx]
		qr_data_phat_hien = qr_data
		qr_found = True
		print(f"[STEP1] Tìm thấy QR Code (ID 0) tại góc bottom-right: ({marker_corners[0][0]:.3f}, {marker_corners[0][1]:.3f})")

	if not qr_found:
		print(f"[STEP1] Không tìm thấy QR ở độ phân giải gốc, thử upscale 3x...")
		new_w = int(region.shape[1] * 3.0)
		new_h = int(region.shape[0] * 3.0)
		region_upscaled = gpu_resize(region, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
		gray_region_upscaled = gpu_cvt_color(region_upscaled, cv2.COLOR_BGR2GRAY)
		qr_data, qr_corners = phat_hien_qr_code(region_upscaled, gray_region_upscaled)

		if qr_data and qr_corners is not None:
			criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
			corners_refined = cv2.cornerSubPix(
				gray_region_upscaled,
				qr_corners.reshape(-1, 1, 2),
				winSize=(5, 5),
				zeroZone=(-1, -1),
				criteria=criteria
			)
			qr_corners = (corners_refined.reshape(4, 2) / 3.0).astype(np.float32)
			qr_corners_full = qr_corners
			qr_ref_point = np.mean(qr_corners_full, axis=0)
			br_idx = np.argmax(qr_corners[:, 0] + qr_corners[:, 1])
			marker_corners[0] = qr_corners[br_idx]
			qr_data_phat_hien = qr_data
			qr_found = True
			print(f"[STEP1] Tìm thấy QR Code (ID 0) sau upscale 3x tại góc bottom-right: ({marker_corners[0][0]:.3f}, {marker_corners[0][1]:.3f})")

	if not qr_found:
		print(f"[STEP1] Không tìm thấy QR sau upscale 3x, thử upscale 5x...")
		new_w = int(region.shape[1] * 5.0)
		new_h = int(region.shape[0] * 5.0)
		region_upscaled = gpu_resize(region, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
		gray_region_upscaled = gpu_cvt_color(region_upscaled, cv2.COLOR_BGR2GRAY)
		qr_data, qr_corners = phat_hien_qr_code(region_upscaled, gray_region_upscaled)

		if qr_data and qr_corners is not None:
			criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
			corners_refined = cv2.cornerSubPix(
				gray_region_upscaled,
				qr_corners.reshape(-1, 1, 2),
				winSize=(5, 5),
				zeroZone=(-1, -1),
				criteria=criteria
			)
			qr_corners = (corners_refined.reshape(4, 2) / 5.0).astype(np.float32)
			qr_corners_full = qr_corners
			qr_ref_point = np.mean(qr_corners_full, axis=0)
			br_idx = np.argmax(qr_corners[:, 0] + qr_corners[:, 1])
			marker_corners[0] = qr_corners[br_idx]
			qr_data_phat_hien = qr_data
			qr_found = True
			print(f"[STEP1] Tìm thấy QR Code (ID 0) sau upscale 5x tại góc bottom-right: ({marker_corners[0][0]:.3f}, {marker_corners[0][1]:.3f})")

	if not qr_found:
		print(f"[STEP1 WARNING] Không tìm thấy QR Code trong vùng Top-Left (đã thử upscale 3x và 5x)")

	# 2) Quét toàn ảnh để lấy 3 marker ArUco cùng ID 17
	shared_markers_corners = detect_shared_aruco_marker_corners(
		img,
		shared_id=SHARED_ARUCO_ID,
		refine_subpixel=True,
	)

	if qr_ref_point is not None and len(shared_markers_corners) >= 3:
		phan_loai = _phan_loai_3_marker_theo_vi_tri(shared_markers_corners, qr_ref_point)
		if phan_loai:
			marker_centers = np.array([
				qr_ref_point,
				[phan_loai['top_right']['center_x'], phan_loai['top_right']['center_y']],
				[phan_loai['bottom_right']['center_x'], phan_loai['bottom_right']['center_y']],
				[phan_loai['bottom_left']['center_x'], phan_loai['bottom_left']['center_y']],
			], dtype=np.float32)
			tam_phieu = np.mean(marker_centers, axis=0)

			if qr_corners_full is not None:
				marker_corners[0] = _chon_goc_gan_tam_nhat(qr_corners_full, tam_phieu)
			marker_corners[1] = _chon_goc_gan_tam_nhat(phan_loai['top_right']['corners'], tam_phieu)
			marker_corners[2] = _chon_goc_gan_tam_nhat(phan_loai['bottom_right']['corners'], tam_phieu)
			marker_corners[3] = _chon_goc_gan_tam_nhat(phan_loai['bottom_left']['corners'], tam_phieu)

			print(f"[STEP1] Đã phân loại marker và chọn góc phía trong theo tâm phiếu")
	
	# Kiểm tra đủ 4 điểm (1 QR + 3 markers)
	if len(marker_corners) < 4:
		found_ids = sorted(marker_corners.keys())
		missing_ids = [i for i in range(4) if i not in marker_corners]
		raise ValueError(f"Cần đủ 4 điểm tham chiếu! Tìm thấy {len(marker_corners)}: {found_ids}. Thiếu: {missing_ids}")
	
	print(f"[STEP1] Tìm thấy đủ 4 điểm tham chiếu (QR + 3 marker ID {SHARED_ARUCO_ID}): {sorted(marker_corners.keys())}")
	
	# Tạo source points (góc markers trên ảnh gốc)
	src_pts = np.array([
		marker_corners[0],  # Top-Left
		marker_corners[1],  # Top-Right
		marker_corners[2],  # Bottom-Right
		marker_corners[3]   # Bottom-Left
	], dtype="float32")

	is_valid_src, src_error = _validate_src_points(src_pts, img.shape)
	if not is_valid_src:
		raise ValueError(
			f"Điểm tham chiếu perspective không hợp lệ: {src_error}. "
			f"src_pts={src_pts.tolist()}"
		)
	
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
	
	# print(f"[STEP1] Kích thước đầu ra (với padding {padding}px): {chieu_rong_pixel_with_padding} x {chieu_dai_pixel_with_padding} pixels")
	
	# Biến đổi perspective (sử dụng GPU nếu có)
	M = cv2.getPerspectiveTransform(src_pts, dst_pts)
	warped = gpu_warp_perspective(img, M, (chieu_rong_pixel_with_padding, chieu_dai_pixel_with_padding))
	
	# Lưu ảnh đầu ra
	success = cv2.imwrite(duong_dan_anh_dau_ra, warped)
	if not success:
		raise ValueError(f"Không thể lưu ảnh tại: {duong_dan_anh_dau_ra}")
	
	# CLEANUP: Giải phóng memory của ảnh gốc (cực kỳ quan trọng!)
	# img có thể lên tới 35-50MB (4000x3000x3 bytes)
	del img
	import gc
	gc.collect()
	
	# print(f"[STEP1] Đã lưu ảnh làm phẳng tại: {duong_dan_anh_dau_ra}")
	print(f"[STEP1] ========== HOÀN THÀNH BƯỚC 1: LÀM PHẲNG ẢNH ==========")
	
	return warped, qr_data_phat_hien
