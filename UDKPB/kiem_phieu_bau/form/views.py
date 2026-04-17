from django.shortcuts import render
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.base import ContentFile
from django.views.decorators.http import require_GET
from django.db import transaction
import json
import os
import subprocess
import tempfile
import math
from datetime import datetime
import cv2
import numpy as np
import qrcode
import time
import random
from pdf2image import convert_from_path
from ballot.doc_qr import (
    SHARED_ARUCO_ID,
    classify_shared_aruco_markers,
    detect_aruco_marker_boxes,
    detect_qr_codes,
)
from .models import BallotDocument
from poll.models import Poll, Candidate
from ballot.models import Ballot
from security.hmac_utils import initialize_poll_hmac_key, create_ballot_with_hmac
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

@require_GET
def ballot_count_api(request, poll_id):
    """API to get ballot count for a poll"""
    try:
        poll = get_object_or_404(Poll, poll_id=poll_id)
        ballot_count = Ballot.objects.filter(poll=poll).count()
        
        return JsonResponse({
            'success': True,
            'count': ballot_count
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_GET
def list_documents_api(request, poll_id):
    """API to get list of BallotDocuments for a poll"""
    try:
        poll = get_object_or_404(Poll, poll_id=poll_id)
        documents = BallotDocument.objects.filter(poll=poll).order_by('-updated_at')
        
        docs_data = []
        for doc in documents:
            docs_data.append({
                'id': doc.id,
                'title': doc.title,
                'updated_at': doc.updated_at.strftime('%d/%m/%Y %H:%M'),
                'created_at': doc.created_at.strftime('%d/%m/%Y %H:%M')
            })
        
        return JsonResponse({
            'success': True,
            'documents': docs_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_GET
def list_candidates_api(request, poll_id):
    """API to get list of Candidates for a poll"""
    try:
        poll = get_object_or_404(Poll, poll_id=poll_id)
        candidates = Candidate.objects.filter(poll=poll).order_by('candidate_id')
        
        candidates_data = []
        for candidate in candidates:
            candidates_data.append({
                'id': candidate.candidate_id,
                'name': candidate.name
            })
        
        return JsonResponse({
            'success': True,
            'candidates': candidates_data,
            'count': len(candidates_data)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def create_ballots_ajax(request, poll_id):
    """Create multiple ballots for a poll via AJAX"""
    try:
        poll = get_object_or_404(Poll, poll_id=poll_id)
        data = json.loads(request.body)
        quantity = int(data.get('quantity', 0))
        
        if quantity <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Số lượng phải lớn hơn 0'
            }, status=400)
        
        if quantity > 1000:
            return JsonResponse({
                'success': False,
                'error': 'Số lượng tối đa là 1000 phiếu'
            }, status=400)
        
        # 1. Khởi tạo HMAC key cho poll nếu chưa có
        if not poll.hmac_secret_key:
            initialize_poll_hmac_key(poll)
        
        # Xóa ballots cũ của poll (nếu có)
        Ballot.objects.filter(poll=poll).delete()
        
        created_ballots = []
        for i in range(quantity):
            # Tạo ballot trống
            ballot = Ballot.objects.create(
                poll=poll,
                # is_checked removed - property now (auto False when counting_status != 'completed')
                is_valid=True
            )
            # Tạo HMAC signature cho ballot
            hmac_signature = create_ballot_with_hmac(ballot, save=True)
            created_ballots.append(ballot.ballot_id)
        
        return JsonResponse({
            'success': True,
            'message': f'Đã tạo thành công {quantity} lá phiếu',
            'ballot_count': quantity,
            'ballot_ids': created_ballots
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def editor_view(request, poll_id=None):
    """Main editor view"""
    context = {}
    if poll_id:
        context['poll_id'] = poll_id
        try:
            poll = Poll.objects.get(poll_id=poll_id)
            context['poll'] = poll
        except Poll.DoesNotExist:
            pass
    return render(request, 'form/editor.html', context)

def _generate_aruco_marker(marker_id, size_px=200, qr_data=None, aruco_id=SHARED_ARUCO_ID):
    """
    Tạo ArUco marker hoặc QR code (cho marker 0)
    
    Args:
        marker_id (int): Vị trí logic của marker (0-3 cho 4 góc)
        size_px (int): Kích thước marker tính bằng pixel
        qr_data (str): Dữ liệu để tạo QR code (cho marker 0)
        aruco_id (int): ID ArUco thực tế dùng cho 3 marker còn lại
        
    Returns:
        str: Đường dẫn đến file ảnh marker tạm thời
    """
    if marker_id == 0 and qr_data:
        # Marker 0 (Top-left): Tạo QR code chứa dữ liệu
        qr = qrcode.QRCode(
            version=None,  # Auto size
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=0.5,  # Giảm border để sát lề hơn
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Tạo image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert PIL image to numpy array và resize
        qr_array = np.array(qr_img.convert('L'))
        qr_resized = cv2.resize(qr_array, (size_px, size_px))
        
        # Tạo tên file unique
        unique_id = f"{int(time.time() * 1000000)}_{random.randint(1000, 9999)}"
        temp_path = os.path.join(tempfile.gettempdir(), f"temp_qr_{marker_id}_{unique_id}.png")
        cv2.imwrite(temp_path, qr_resized)
        return temp_path
    else:
        # Các marker khác (1, 2, 3): ArUco thuần (dùng chung 1 ID)
        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, aruco_id, size_px)
        
        # Tạo tên file unique
        unique_id = f"{int(time.time() * 1000000)}_{random.randint(1000, 9999)}"
        temp_path = os.path.join(tempfile.gettempdir(), f"temp_aruco_{aruco_id}_{marker_id}_{unique_id}.png")
        cv2.imwrite(temp_path, marker_img)
        return temp_path


@csrf_exempt
@require_http_methods(["POST"])
def compile_pdf(request):
    """Compile Ballot form to PDF and return the PDF file"""
    try:
        data = json.loads(request.body)
        
        # Extract data from request
        margins = data.get('margins', {})
        font_family = data.get('fontFamily', 'Arial')
        font_size = data.get('fontSize', 12)
        header_rows = data.get('headerRows', [])
        title_rows = data.get('titleRows', [])
        body_rows = data.get('bodyRows', [])
        footer_rows = data.get('footerRows', [])
        
        # Generate LaTeX content
        latex_content = generate_latex(
            margins, font_family, font_size,
            header_rows, title_rows, body_rows, footer_rows
        )
        
        # Create temporary directory for LaTeX compilation
        with tempfile.TemporaryDirectory() as temp_dir:
            tex_file = os.path.join(temp_dir, 'document.tex')
            pdf_file = os.path.join(temp_dir, 'document.pdf')
            
            # Write LaTeX content to file
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(latex_content)
            
            # Compile LaTeX to PDF using pdflatex
            try:
                result = subprocess.run(
                    ['pdflatex', '-interaction=nonstopmode', 'document.tex'],
                    capture_output=True,
                    text=False,
                    timeout=30,
                    cwd=temp_dir
                )
                
                # Check if PDF was generated
                if os.path.exists(pdf_file):
                    # Read PDF file into memory
                    with open(pdf_file, 'rb') as f:
                        pdf_data = f.read()
                    
                    # Return PDF as response from memory
                    from io import BytesIO
                    response = FileResponse(
                        BytesIO(pdf_data),
                        content_type='application/pdf'
                    )
                    response['Content-Disposition'] = 'inline; filename="document.pdf"'
                    return response
                else:
                    log_output = ''
                    try:
                        log_output = result.stdout.decode('utf-8', errors='ignore') + result.stderr.decode('utf-8', errors='ignore')
                    except:
                        log_output = str(result.stdout) + str(result.stderr)
                    return JsonResponse({
                        'success': False,
                        'error': 'PDF generation failed',
                        'log': log_output
                    }, status=500)
                    
            except subprocess.TimeoutExpired:
                return JsonResponse({
                    'success': False,
                    'error': 'PDF generation timeout'
                }, status=500)
            except FileNotFoundError:
                return JsonResponse({
                    'success': False,
                    'error': 'pdflatex not found. Please install TeX Live or MiKTeX.'
                }, status=500)
                
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def save_document(request):
    """Save document configuration and compile PDF to database"""
    try:
        data = json.loads(request.body)
        
        title = data.get('title', 'Untitled Document')
        margins = data.get('margins', {})
        font_family = data.get('fontFamily', 'Arial')
        font_size = data.get('fontSize', 12)
        header_rows = data.get('headerRows', [])
        title_rows = data.get('titleRows', [])
        body_rows = data.get('bodyRows', [])
        footer_rows = data.get('footerRows', [])
        poll_id = data.get('pollId')  # Optional poll ID
        
        # Set poll if provided and delete old documents
        poll = None
        if poll_id:
            from poll.models import Poll
            try:
                poll = Poll.objects.get(poll_id=poll_id)
                # Xóa tất cả BallotDocument cũ của poll này (PDF files sẽ tự động xóa)
                BallotDocument.objects.filter(poll=poll).delete()
            except Poll.DoesNotExist:
                pass
        
        # Create new document
        doc = BallotDocument()
        if request.user.is_authenticated:
            doc.user = request.user
        
        doc.title = title
        doc.margin_top = margins.get('top', 2.0)
        doc.margin_bottom = margins.get('bottom', 2.0)
        doc.margin_left = margins.get('left', 2.0)
        doc.margin_right = margins.get('right', 2.0)
        doc.font_family = font_family
        doc.font_size = font_size
        doc.header_content = header_rows
        doc.title_content = title_rows
        doc.body_content = body_rows
        doc.footer_content = footer_rows
        
        # Assign poll to document
        if poll:
            doc.poll = poll
        
        # Lấy danh sách ballot và tạo qr_data
        qr_data_list = []
        if poll:
            ballots = Ballot.objects.filter(poll=poll).order_by('ballot_id')
            for ballot in ballots:
                # Format: 0:ballot_id:qr_hmac
                qr_data = f"0:{ballot.ballot_id}:{ballot.qr_hmac or ''}"
                qr_data_list.append(qr_data)
        
        # Nếu không có ballot, tạo 1 trang mẫu
        if not qr_data_list:
            qr_data_list = ["qrmaucuadomanhnghia"]
        
        # Generate LaTeX content with multiple pages
        latex_content = generate_latex_multi_page(
            margins, font_family, font_size,
            header_rows, title_rows, body_rows, footer_rows,
            qr_data_list
        )
        
        # Create temporary directory for LaTeX compilation
        with tempfile.TemporaryDirectory() as temp_dir:
            tex_file = os.path.join(temp_dir, 'ballot.tex')
            pdf_file = os.path.join(temp_dir, 'ballot.pdf')
            
            # Write LaTeX content to file
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(latex_content)
            
            # Compile LaTeX to PDF using pdflatex
            try:
                result = subprocess.run(
                    ['pdflatex', '-interaction=nonstopmode', 'ballot.tex'],
                    capture_output=True,
                    text=False,
                    timeout=60,  # Tăng timeout cho nhiều trang
                    cwd=temp_dir
                )
                
                # Check if PDF was generated
                if not os.path.exists(pdf_file):
                    log_output = ''
                    try:
                        log_output = result.stdout.decode('utf-8', errors='ignore') + result.stderr.decode('utf-8', errors='ignore')
                    except:
                        log_output = str(result.stdout) + str(result.stderr)
                    return JsonResponse({
                        'success': False,
                        'error': 'PDF generation failed',
                        'log': log_output
                    }, status=500)
                
                # Read PDF file into memory
                with open(pdf_file, 'rb') as f:
                    pdf_data = f.read()
                
                # Bọc trong transaction để rollback khi có lỗi
                try:
                    with transaction.atomic():
                        # Save PDF to model
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f'ballot_{timestamp}.pdf'
                        doc.pdf_file.save(filename, ContentFile(pdf_data), save=False)
                        
                        # Calculate marker distances from actual PDF
                        distances = calculate_marker_distances_from_pdf(pdf_file, dpi=300)
                        if not distances.get('success'):
                            error_msg = distances.get('error', 'Không thể tính khoảng cách markers')
                            print(f"\n❌ LỖI: {error_msg}")
                            raise Exception(f"Không thể đọc markers từ PDF: {error_msg}")
                        
                        doc.marker_distance_horizontal = distances['horizontal']
                        doc.marker_distance_vertical = distances['vertical']
                        
                        # Save document
                        doc.save()
                        
                        print(f"\n✅ Đã lưu document thành công với marker distances: H={distances['horizontal']}cm, V={distances['vertical']}cm\n")
                
                except Exception as e:
                    print(f"\n❌ Transaction rolled back due to error: {str(e)}\n")
                    return JsonResponse({
                        'success': False,
                        'error': str(e)
                    }, status=500)
                
                # Return PDF as response
                from io import BytesIO
                response = FileResponse(
                    BytesIO(pdf_data),
                    content_type='application/pdf'
                )
                response['Content-Disposition'] = f'inline; filename="{filename}"'
                return response
                
            except subprocess.TimeoutExpired:
                return JsonResponse({
                    'success': False,
                    'error': 'PDF generation timeout'
                }, status=500)
            except FileNotFoundError:
                return JsonResponse({
                    'success': False,
                    'error': 'pdflatex not found. Please install TeX Live or MiKTeX.'
                }, status=500)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
def load_document(request, doc_id):
    """Load document configuration from database"""
    try:
        doc = BallotDocument.objects.get(id=doc_id)
        
        return JsonResponse({
            'success': True,
            'data': {
                'id': doc.id,
                'title': doc.title,
                'margins': {
                    'top': doc.margin_top,
                    'bottom': doc.margin_bottom,
                    'left': doc.margin_left,
                    'right': doc.margin_right
                },
                'fontFamily': doc.font_family,
                'fontSize': doc.font_size,
                'headerRows': doc.header_content,
                'titleRows': doc.title_content,
                'bodyRows': doc.body_content,
                'footerRows': doc.footer_content
            }
        })
        
    except BallotDocument.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Document not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def generate_latex_multi_page(margins, font_family, font_size, header_rows, title_rows, body_rows, footer_rows, qr_data_list):
    """Generate LaTeX content with multiple pages (one per ballot)"""
    
    # Map font families
    font_map = {
        'Arial': 'helvet',
        'Times New Roman': 'times',
        'Courier': 'courier',
        'Computer Modern': ''
    }
    
    latex_font = font_map.get(font_family, '')
    
    # Start LaTeX document with Vietnamese support
    latex = r'''\documentclass[''' + str(font_size) + r'''pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T5]{fontenc}
\usepackage[vietnamese]{babel}
'''
    
    if latex_font:
        latex += r'\usepackage{' + latex_font + r'}' + '\n'
        if latex_font == 'helvet':
            latex += r'\renewcommand{\familydefault}{\sfdefault}' + '\n'
    
    # Get margin values
    margin_top = margins.get('top', 2)
    margin_bottom = margins.get('bottom', 2)
    margin_left = margins.get('left', 2)
    margin_right = margins.get('right', 2)
    
    latex += r'''\usepackage[
    top=''' + str(margin_top) + r'''cm,
    bottom=''' + str(margin_bottom) + r'''cm,
    left=''' + str(margin_left) + r'''cm,
    right=''' + str(margin_right) + r'''cm
]{geometry}
\usepackage{graphicx}
\usepackage{array}
\usepackage{framed}
\usepackage{eso-pic}
\usepackage{calc}
\usepackage{tikz}
\usetikzlibrary{calc}
\pagestyle{empty}

% Tăng độ đậm đường kẻ bảng
\setlength{\arrayrulewidth}{1.8pt}

\begin{document}

'''
    
    # Generate a page for each ballot
    for page_idx, qr_data in enumerate(qr_data_list):
        # Generate markers for this page
        marker_paths = []
        for marker_id in range(4):
            if marker_id == 0:
                # QR code cho marker 0 với qr_data cụ thể
                marker_path = _generate_aruco_marker(marker_id, size_px=200, qr_data=qr_data)
            else:
                # 3 marker ArUco dùng chung ID 17
                marker_path = _generate_aruco_marker(marker_id, size_px=200)
            marker_paths.append(marker_path)
        
        # Add page content with markers
        latex += r'''% Page ''' + str(page_idx + 1) + r'''
\AddToShipoutPictureBG*{%
    % Top-left corner (QR code) - sát góc nội dung
    \AtPageLowerLeft{%
        \put(\LenToUnit{''' + str(margin_left) + r'''cm-1.8cm},\LenToUnit{\paperheight-''' + str(margin_top) + r'''cm}){%
            \includegraphics[width=1.8cm,height=1.8cm]{''' + marker_paths[0].replace('\\', '/') + r'''}%
        }%
    }%
    % Top-right corner (ArUco shared ID 17) - sát góc nội dung
    \AtPageLowerLeft{%
        \put(\LenToUnit{\paperwidth-''' + str(margin_right) + r'''cm},\LenToUnit{\paperheight-''' + str(margin_top) + r'''cm}){%
            \includegraphics[width=1.0cm,height=1.0cm]{''' + marker_paths[1].replace('\\', '/') + r'''}%
        }%
    }%
}

'''
        
        # Add header content (Quốc hiệu tiêu ngữ)
        if header_rows:
            for row in header_rows:
                latex += format_row(row) + '\n\n'
        
        # Add title content
        if title_rows:
            for row in title_rows:
                latex += format_row(row) + '\n\n'
        
        # Add body content
        if body_rows:
            for row in body_rows:
                latex += format_row(row) + '\n\n'
        
        # Add footer content
        if footer_rows:
            for row in footer_rows:
                latex += format_row(row) + '\n\n'
        
        # Add bottom markers
        latex += r'''
\vspace{0.5cm}

% Bottom markers - using simple hbox positioning
\noindent
\rlap{\hspace{-1.0cm}\includegraphics[width=1.0cm,height=1.0cm]{''' + marker_paths[3].replace('\\', '/') + r'''}}%
\hfill
\llap{\includegraphics[width=1.0cm,height=1.0cm]{''' + marker_paths[2].replace('\\', '/') + r'''}\hspace{-1.0cm}}

'''
        
        # Add page break if not last page
        if page_idx < len(qr_data_list) - 1:
            latex += r'\clearpage' + '\n\n'
    
    latex += r'\end{document}'
    
    return latex

def calculate_marker_distances_from_pdf(pdf_path, dpi=300):
    """
    Tính khoảng cách thực tế giữa các markers từ PDF (tính từ 2 biên gần nhất)
    
    Cấu hình markers:
    - Top-left: QR code
    - Top-right, Bottom-right, Bottom-left: 3 ArUco cùng ID 17
    
    Args:
        pdf_path (str): Đường dẫn đến file PDF
        dpi (int): DPI để convert PDF sang ảnh (mặc định 300)
    
    Returns:
        dict: Dictionary chứa các khoảng cách thực tế tính bằng cm:
            - horizontal: Khoảng cách ngang (từ biên phải của marker trái đến biên trái của marker phải)
            - vertical: Khoảng cách dọc (từ biên dưới của marker trên đến biên trên của marker dưới)
            - success: True nếu tính toán thành công
            - error: Thông báo lỗi nếu có
    """
    try:
        # Convert PDF sang ảnh (chỉ lấy trang đầu tiên)
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=1)
        
        if not images:
            return {
                'success': False,
                'error': 'Không thể convert PDF sang ảnh'
            }
        
        # Convert PIL Image sang numpy array cho OpenCV
        image = np.array(images[0])
        # Convert RGB sang BGR (OpenCV format)
        image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        # Detect ArUco markers (giữ đủ marker trùng ID)
        marker_boxes = detect_aruco_marker_boxes(image_bgr, refine_subpixel=False)
        
        # Detect QR codes
        qr_codes = detect_qr_codes(image_bgr)
        
        # Pixel per cm (dựa trên DPI)
        # 1 inch = 2.54 cm, 1 inch = dpi pixels => 1 cm = dpi/2.54 pixels
        pixels_per_cm = dpi / 2.54
        
        # Xác định vị trí các markers
        markers_info = {
            'aruco_markers': []
        }
        
        # QR code (thường ở top-left, marker_id=0)
        if qr_codes:
            qr = qr_codes[0]  # Lấy QR đầu tiên
            rect = qr['rect']
            markers_info['qr'] = {
                'left': rect['left'],
                'right': rect['left'] + rect['width'],
                'top': rect['top'],
                'bottom': rect['top'] + rect['height'],
                'center_x': rect['left'] + rect['width'] / 2.0,
                'center_y': rect['top'] + rect['height'] / 2.0,
                'type': 'qr'
            }
        
        for box in marker_boxes:
            box['type'] = 'aruco'
            markers_info['aruco_markers'].append(box)

        # Top-left: ưu tiên QR, fallback ArUco 0 để tương thích cũ
        top_left = None
        top_right = None
        bottom_left = None
        bottom_right = None
        
        image_height, image_width = image.shape[:2]
        
        # QR code là top-left
        if 'qr' in markers_info:
            top_left = markers_info['qr']
        else:
            legacy_top_left = [box for box in marker_boxes if box['id'] == 0]
            if legacy_top_left:
                top_left = legacy_top_left[0]

        # Tương thích ngược: nếu PDF cũ có marker ID 1/2/3 thì dùng luôn
        legacy_top_right = [box for box in marker_boxes if box['id'] == 1]
        legacy_bottom_right = [box for box in marker_boxes if box['id'] == 2]
        legacy_bottom_left = [box for box in marker_boxes if box['id'] == 3]

        if legacy_top_right and legacy_bottom_right and legacy_bottom_left:
            top_right = legacy_top_right[0]
            bottom_right = legacy_bottom_right[0]
            bottom_left = legacy_bottom_left[0]
        else:
            # Luồng mới: 3 marker cùng ID 17, phân loại theo vị trí tương đối với QR
            shared_markers = [box for box in marker_boxes if box['id'] == SHARED_ARUCO_ID]
            if top_left and len(shared_markers) >= 3:
                top_right, bottom_right, bottom_left = classify_shared_aruco_markers(shared_markers, top_left)
        
        # Kiểm tra đủ markers
        missing_markers = []
        if not top_left:
            missing_markers.append('top-left')
        if not top_right:
            missing_markers.append('top-right')
        if not bottom_left:
            missing_markers.append('bottom-left')
        if not bottom_right:
            missing_markers.append('bottom-right')
        
        if missing_markers:
            return {
                'success': False,
                'error': f'Thiếu markers: {", ".join(missing_markers)}',
                'markers_info': markers_info
            }

        # Chuẩn hóa lại thứ tự marker đáy theo trục X để tránh swap BR/BL
        # (có thể xảy ra khi 3 marker dùng chung ID 17 và kết quả detect không ổn định)
        if bottom_left['center_x'] > bottom_right['center_x']:
            bottom_left, bottom_right = bottom_right, bottom_left
        
        # Tính khoảng cách ngang (từ biên phải của marker trái đến biên trái của marker phải)
        # Lấy trung bình của khoảng cách trên và dưới
        horizontal_top_px = top_right['left'] - top_left['right']
        horizontal_bottom_px = bottom_right['left'] - bottom_left['right']
        horizontal_px = (horizontal_top_px + horizontal_bottom_px) / 2
        horizontal_cm = horizontal_px / pixels_per_cm
        
        # Tính khoảng cách dọc (từ biên dưới của marker trên đến biên trên của marker dưới)
        # Lấy trung bình của khoảng cách trái và phải
        vertical_left_px = bottom_left['top'] - top_left['bottom']
        vertical_right_px = bottom_right['top'] - top_right['bottom']
        vertical_px = (vertical_left_px + vertical_right_px) / 2
        vertical_cm = vertical_px / pixels_per_cm

        # Khoảng cách marker phải dương; nếu âm hoặc bằng 0 thì marker đã bị phân loại sai
        if horizontal_top_px <= 0 or horizontal_bottom_px <= 0 or vertical_left_px <= 0 or vertical_right_px <= 0:
            return {
                'success': False,
                'error': (
                    'Khoảng cách marker không hợp lệ '
                    f'(H_top={horizontal_top_px:.2f}, H_bottom={horizontal_bottom_px:.2f}, '
                    f'V_left={vertical_left_px:.2f}, V_right={vertical_right_px:.2f})'
                ),
                'markers_found': {
                    'top_left': top_left,
                    'top_right': top_right,
                    'bottom_left': bottom_left,
                    'bottom_right': bottom_right
                }
            }
        
        return {
            'success': True,
            'horizontal': round(horizontal_cm, 2),
            'vertical': round(vertical_cm, 2),
            'horizontal_top_px': round(horizontal_top_px, 2),
            'horizontal_bottom_px': round(horizontal_bottom_px, 2),
            'vertical_left_px': round(vertical_left_px, 2),
            'vertical_right_px': round(vertical_right_px, 2),
            'dpi': dpi,
            'pixels_per_cm': round(pixels_per_cm, 2),
            'image_size': {'width': image_width, 'height': image_height},
            'markers_found': {
                'top_left': top_left,
                'top_right': top_right,
                'bottom_left': bottom_left,
                'bottom_right': bottom_right
            },
            'note': 'Khoảng cách đo từ 2 biên gần nhất của các markers (hỗ trợ marker chung ID 17 và định dạng cũ)'
        }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Lỗi khi tính toán: {str(e)}'
        }


def generate_latex(margins, font_family, font_size, header_rows, title_rows, body_rows, footer_rows):
    """Generate LaTeX content from ballot form data"""
    
    # Generate markers (QR cho góc trái trên, 3 ArUco còn lại dùng chung ID 17)
    marker_paths = []
    for marker_id in range(4):
        if marker_id == 0:
            # QR code cho marker 0
            marker_path = _generate_aruco_marker(marker_id, size_px=200, qr_data="qrmaucuadomanhnghia")
        else:
            # 3 marker ArUco dùng chung ID 17
            marker_path = _generate_aruco_marker(marker_id, size_px=200)
        marker_paths.append(marker_path)
    
    # Map font families
    font_map = {
        'Arial': 'helvet',
        'Times New Roman': 'times',
        'Courier': 'courier',
        'Computer Modern': ''
    }
    
    latex_font = font_map.get(font_family, '')
    
    # Start LaTeX document with Vietnamese support
    latex = r'''\documentclass[''' + str(font_size) + r'''pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T5]{fontenc}
\usepackage[vietnamese]{babel}
'''
    
    if latex_font:
        latex += r'\usepackage{' + latex_font + r'}' + '\n'
        if latex_font == 'helvet':
            latex += r'\renewcommand{\familydefault}{\sfdefault}' + '\n'
    
    # Get margin values
    margin_top = margins.get('top', 2)
    margin_bottom = margins.get('bottom', 2)
    margin_left = margins.get('left', 2)
    margin_right = margins.get('right', 2)
    
    latex += r'''\usepackage[
    top=''' + str(margin_top) + r'''cm,
    bottom=''' + str(margin_bottom) + r'''cm,
    left=''' + str(margin_left) + r'''cm,
    right=''' + str(margin_right) + r'''cm
]{geometry}
\usepackage{graphicx}
\usepackage{array}
\usepackage{framed}
\usepackage{eso-pic}
\usepackage{calc}
\usepackage{tikz}
\usetikzlibrary{calc}
\pagestyle{empty}

% Tăng độ đậm đường kẻ bảng
\setlength{\arrayrulewidth}{1.8pt}

\begin{document}

% Add top markers (fixed position)
\AddToShipoutPictureBG{%
    % Top-left corner (QR code) - sát góc nội dung
    \AtPageLowerLeft{%
        \put(\LenToUnit{''' + str(margin_left) + r'''cm-1.8cm},\LenToUnit{\paperheight-''' + str(margin_top) + r'''cm}){%
            \includegraphics[width=1.8cm,height=1.8cm]{''' + marker_paths[0].replace('\\', '/') + r'''}%
        }%
    }%
    % Top-right corner (ArUco shared ID 17) - sát góc nội dung
    \AtPageLowerLeft{%
        \put(\LenToUnit{\paperwidth-''' + str(margin_right) + r'''cm},\LenToUnit{\paperheight-''' + str(margin_top) + r'''cm}){%
            \includegraphics[width=1.0cm,height=1.0cm]{''' + marker_paths[1].replace('\\', '/') + r'''}%
        }%
    }%
}

'''
    
    # Add header content (Quốc hiệu tiêu ngữ)
    if header_rows:
        for row in header_rows:
            latex += format_row(row) + '\n\n'
    
    # Add title content
    if title_rows:
        for row in title_rows:
            latex += format_row(row) + '\n\n'
    
    # Add body content
    if body_rows:
        for row in body_rows:
            latex += format_row(row) + '\n\n'
    
    # Add footer content
    if footer_rows:
        for row in footer_rows:
            latex += format_row(row) + '\n\n'
    
    # Add bottom markers - simple approach with exact positioning
    latex += r'''
\vspace{0.5cm}

% Bottom markers - using simple hbox positioning
\noindent
\rlap{\hspace{-1.0cm}\includegraphics[width=1.0cm,height=1.0cm]{''' + marker_paths[3].replace('\\', '/') + r'''}}%
\hfill
\llap{\includegraphics[width=1.0cm,height=1.0cm]{''' + marker_paths[2].replace('\\', '/') + r'''}\hspace{-1.0cm}}

'''
    
    latex += r'\end{document}'
    
    return latex

def format_row(row):
    """Format a single row for PDF generation"""
    if not row:
        return ''
    
    row_type = row.get('type', 'single')
    columns = row.get('columns', [])
    
    if not columns and row_type not in ['table', 'table-double', 'frame', 'frame-double']:
        return ''
    
    # Handle table types
    if row_type == 'table':
        return format_table(row, False)
    elif row_type == 'table-double':
        return format_table(row, True)
    
    # Handle frame types
    elif row_type == 'frame':
        return format_frame(row, False)
    elif row_type == 'frame-double':
        return format_frame(row, True)
    
    # Handle single column row
    elif row_type == 'single':
        col = columns[0] if columns else {}
        text = col.get('text', '')
        return format_text(text, col)
    
    # Handle double column row
    else:
        if len(columns) >= 2:
            left_col = columns[0]
            right_col = columns[1]
            left_text = format_text(left_col.get('text', ''), left_col)
            right_text = format_text(right_col.get('text', ''), right_col)
            
            return r'\noindent\begin{minipage}[t]{0.48\textwidth}' + '\n' + \
                   left_text + '\n' + \
                   r'\end{minipage}\hfill' + '\n' + \
                   r'\begin{minipage}[t]{0.48\textwidth}' + '\n' + \
                   right_text + '\n' + \
                   r'\end{minipage}'
        else:
            col = columns[0] if columns else {}
            text = col.get('text', '')
            return format_text(text, col)

def format_table(row, is_double):
    """Format a table with borders (dòng kẻ)"""
    margin = row.get('margin', 0)
    num_cols = row.get('numCols', 1)
    nested_rows = row.get('nestedRows', [])
    double_mode = row.get('doubleMode', 'margin')  # 'margin' or 'center'
    column_widths = row.get('columnWidths', [])  # % widths for each column
    row_height = row.get('rowHeight', 1.0)  # Row height multiplier (default 1.0)
    
    if not nested_rows:
        return ''
    
    # Validate and normalize column widths
    if not column_widths or len(column_widths) != num_cols:
        # Default to equal widths
        equal_width = 100.0 / num_cols
        column_widths = [equal_width] * num_cols
    
    # Ensure percentages sum to 100%
    total = sum(column_widths)
    if total > 0:
        column_widths = [w / total * 100 for w in column_widths]
    
    # Ensure row height is within reasonable bounds
    row_height = max(1.0, min(5.0, float(row_height)))
    
    # Build column specification with calculated width
    # Calculate available width and distribute among columns
    if is_double:
        # For double table, use proportional width within minipage (48% of textwidth)
        # Calculate width for each column based on percentage
        col_specs = []
        for width_pct in column_widths:
            col_width_expr = f'\\dimexpr({width_pct/100}\\linewidth-{1}\\arrayrulewidth-{2}\\tabcolsep)\\relax'
            col_specs.append(f'p{{{col_width_expr}}}')
        col_spec = '|' + '|'.join(col_specs) + '|'
    else:
        # For single table
        if margin > 0:
            # Will be wrapped in minipage, use linewidth
            col_specs = []
            for width_pct in column_widths:
                col_width_expr = f'\\dimexpr({width_pct/100}\\linewidth-{1}\\arrayrulewidth-{2}\\tabcolsep)\\relax'
                col_specs.append(f'p{{{col_width_expr}}}')
            col_spec = '|' + '|'.join(col_specs) + '|'
        else:
            # No margin, use textwidth directly
            col_specs = []
            for width_pct in column_widths:
                col_width_expr = f'\\dimexpr({width_pct/100}\\textwidth-{1}\\arrayrulewidth-{2}\\tabcolsep)\\relax'
                col_specs.append(f'p{{{col_width_expr}}}')
            col_spec = '|' + '|'.join(col_specs) + '|'
    
    # Build table content with row height adjustment
    # Use \renewcommand{\arraystretch}{row_height} to increase row height
    table_content = ''
    if row_height != 1.0:
        table_content += f'{{\\renewcommand{{\\arraystretch}}{{{row_height}}}\n'
    
    table_content += f'\\begin{{tabular}}{{{col_spec}}}\n'
    table_content += '\\hline\n'
    
    # Add each nested row
    for nested_row in nested_rows:
        row_cells = []
        for col in nested_row.get('columns', []):
            cell_text = format_text(col.get('text', ''), col)
            row_cells.append(cell_text)
        
        # Fill missing columns with empty cells
        while len(row_cells) < num_cols:
            row_cells.append('')
        
        table_content += ' & '.join(row_cells[:num_cols]) + ' \\\\\n'
        table_content += '\\hline\n'
    
    table_content += '\\end{tabular}\n'
    if row_height != 1.0:
        table_content += '}\n'  # Close the arraystretch group
    
    if is_double:
        # Create two tables side by side with different modes
        if double_mode == 'center':
            # Căn giữa: (lề 1 + lề 2) / 2 = khoảng cách lề trái = lề phải = khoảng cách giữa
            spacing = margin  # (margin1 + margin2) / 2, assuming margin1 = margin2 = margin
            # Calculate minipage width: (textwidth - 4*spacing) / 2
            minipage_width = f'\\dimexpr(\\textwidth-{spacing * 4}cm)/2\\relax'
            return f'\\noindent\\hspace{{{spacing}cm}}' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   table_content + '\n' + \
                   f'\\end{{minipage}}\\hspace{{{spacing * 2}cm}}' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   table_content + '\n' + \
                   '\\end{minipage}\\n'
        else:
            # Căn lề: Bảng 1 dính lề trái, Bảng 2 dính lề phải, khoảng giữa = lề 1 + lề 2
            spacing = margin * 2  # gap between two tables
            # Calculate minipage width: (textwidth - spacing) / 2
            minipage_width = f'\\dimexpr(\\textwidth-{spacing}cm)/2\\relax'
            return '\\noindent' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   table_content + '\n' + \
                   f'\\end{{minipage}}\\hspace{{{spacing}cm}}' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   table_content + '\n' + \
                   '\\end{minipage}\\n'
    else:
        # Single table with margin - căn lùi cả 2 bên
        if margin > 0:
            # Calculate table width after applying margin on both sides
            table_width = f'\\dimexpr\\textwidth-{margin * 2}cm\\relax'
            return f'\\noindent\\hspace{{{margin}cm}}\n' + \
                   f'\\begin{{minipage}}{{{table_width}}}\n' + \
                   table_content + \
                   '\\end{minipage}\n'
        else:
            return '\\noindent\n' + table_content

def format_frame(row, is_double):
    """Format a frame with border but without internal lines (có viền bao quanh, không có dòng kẻ bên trong)"""
    margin = row.get('margin', 0)
    num_cols = row.get('numCols', 1)
    nested_rows = row.get('nestedRows', [])
    double_mode = row.get('doubleMode', 'margin')  # 'margin' or 'center'
    column_widths = row.get('columnWidths', [])  # % widths for each column
    
    if not nested_rows:
        return ''
    
    # Validate and normalize column widths
    if not column_widths or len(column_widths) != num_cols:
        # Default to equal widths
        equal_width = 100.0 / num_cols
        column_widths = [equal_width] * num_cols
    
    # Ensure percentages sum to 100%
    total = sum(column_widths)
    if total > 0:
        column_widths = [w / total * 100 for w in column_widths]
    
    # Build frame content - start with \noindent to prevent paragraph indentation
    frame_content = '\\noindent\n'
    
    # Add each nested row with indentation
    for idx, nested_row in enumerate(nested_rows):
        # All rows use same indent pattern
        indent = '\\hspace{0.5cm}'
        
        if num_cols == 1:
            # Single column - just format normally with indent
            col = nested_row.get('columns', [{}])[0]
            cell_text = format_text(col.get('text', ''), col)
            frame_content += indent + cell_text + '\\\\\n'
        else:
            # Multiple columns - use minipage for each column with custom widths
            frame_content += indent
            columns_data = nested_row.get('columns', [])
            
            for col_idx, col in enumerate(columns_data[:num_cols]):
                cell_text = format_text(col.get('text', ''), col)
                # Use percentage width (0.85 factor to leave some margin)
                col_width_pct = column_widths[col_idx] / 100 * 0.85
                
                if col_idx > 0:
                    frame_content += '\\hfill'
                frame_content += f'\\begin{{minipage}}[t]{{{col_width_pct:.4f}\\linewidth}}\n'
                frame_content += cell_text + '\n'
                frame_content += '\\end{minipage}'
            
            frame_content += '\\\\\n'
    
    # Wrap content in framed environment
    if is_double:
        # Create two frames side by side with different modes
        single_frame = '\\begin{framed}\n' + frame_content + '\\end{framed}'
        
        if double_mode == 'center':
            # Căn giữa: (lề 1 + lề 2) / 2 = khoảng cách lề trái = lề phải = khoảng cách giữa
            spacing = margin  # (margin1 + margin2) / 2, assuming margin1 = margin2 = margin
            # Calculate minipage width: (textwidth - 4*spacing) / 2
            minipage_width = f'\\dimexpr(\\textwidth-{spacing * 4}cm)/2\\relax'
            return f'\\noindent\\hspace{{{spacing}cm}}' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   single_frame + '\n' + \
                   f'\\end{{minipage}}\\hspace{{{spacing * 2}cm}}' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   single_frame + '\n' + \
                   '\\end{minipage}\\n'
        else:
            # Căn lề: Khung 1 dính lề trái, Khung 2 dính lề phải, khoảng giữa = lề 1 + lề 2
            spacing = margin * 2  # gap between two frames
            # Calculate minipage width: (textwidth - spacing) / 2
            minipage_width = f'\\dimexpr(\\textwidth-{spacing}cm)/2\\relax'
            return '\\noindent' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   single_frame + '\n' + \
                   f'\\end{{minipage}}\\hspace{{{spacing}cm}}' + '\n' + \
                   f'\\begin{{minipage}}[t]{{{minipage_width}}}' + '\n' + \
                   single_frame + '\n' + \
                   '\\end{minipage}\\n'
    else:
        # Single frame with margin - căn lùi cả 2 bên
        if margin > 0:
            # Use minipage to control width when margin is set
            frame_width = f'\\dimexpr\\textwidth-{margin * 2}cm\\relax'
            return f'\\noindent\\hspace{{{margin}cm}}\n' + \
                   f'\\begin{{minipage}}{{{frame_width}}}\n' + \
                   '\\begin{framed}\n' + \
                   frame_content + \
                   '\\end{framed}\n' + \
                   '\\end{minipage}'
        else:
            return '\\noindent\n' + \
                   '\\begin{framed}\n' + \
                   frame_content + \
                   '\\end{framed}'

def format_text(text, style):
    """Apply text formatting based on style"""
    if not text:
        return ''
    
    # Escape special characters for PDF generation
    text = text.replace('\\', '\\textbackslash{}')
    text = text.replace('&', '\\&')
    text = text.replace('%', '\\%')
    text = text.replace('$', '\\$')
    text = text.replace('#', '\\#')
    text = text.replace('_', '\\_')
    text = text.replace('{', '\\{')
    text = text.replace('}', '\\}')
    text = text.replace('~', '\\textasciitilde{}')
    text = text.replace('^', '\\textasciicircum{}')
    
    # Apply formatting
    if style.get('bold'):
        text = r'\textbf{' + text + '}'
    if style.get('italic'):
        text = r'\textit{' + text + '}'
    if style.get('underline'):
        text = r'\underline{' + text + '}'
    
    # Apply alignment
    alignment = style.get('align', 'left')
    if alignment == 'center':
        text = r'\begin{center}' + text + r'\end{center}'
    elif alignment == 'right':
        text = r'\begin{flushright}' + text + r'\end{flushright}'
    
    # Apply font size
    font_size = style.get('fontSize')
    if font_size:
        size_commands = {
            8: r'\tiny',
            10: r'\footnotesize',
            12: r'\normalsize',
            14: r'\large',
            16: r'\Large',
            18: r'\LARGE',
            20: r'\huge',
            24: r'\Huge'
        }
        size_cmd = size_commands.get(int(font_size), r'\normalsize')
        text = '{' + size_cmd + ' ' + text + '}'
    
    return text
