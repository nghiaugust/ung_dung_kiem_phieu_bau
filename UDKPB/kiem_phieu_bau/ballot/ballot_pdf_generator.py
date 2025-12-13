"""
Module tạo phiếu bầu dạng PDF với form có thể tùy chỉnh
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import os
import sys
import cv2
import numpy as np


class BallotPDFGenerator:
    """
    Class tạo phiếu bầu dạng PDF với khả năng tùy chỉnh cao
    
    Ví dụ sử dụng:
    ```python
    generator = BallotPDFGenerator(
        title="PHIẾU BẦU CỬ ĐẠI BIỂU QUỐC HỘI",
        header_info={
            "Đơn vị": "Trường Đại học ABC",
            "Kỳ bầu cử": "Năm 2024",
            "Ngày bầu cử": "15/12/2024"
        }
    )
    
    generator.set_table_config(
        columns=["STT", "Họ và tên", "Năm sinh", "Chọn"],
        column_widths=[1*cm, 6*cm, 2*cm, 2*cm]
    )
    
    data = [
        ["1", "Nguyễn Văn A", "1980", "☐"],
        ["2", "Trần Thị B", "1985", "☐"],
    ]
    
    pdf_buffer = generator.generate(data)
    ```
    """
    
    def __init__(self, title="PHIẾU BẦU CỬ", header_info=None, footer_text=None, 
                 page_size=A4, font_path=None, add_aruco_markers=False, aruco_size=1.5):
        """
        Khởi tạo BallotPDFGenerator
        
        Args:
            title (str): Tiêu đề phiếu bầu
            header_info (dict): Thông tin header dạng {key: value}
            footer_text (str): Text chân trang
            page_size: Kích thước trang (mặc định A4)
            font_path (str): Đường dẫn đến file font Unicode (nếu cần)
            add_aruco_markers (bool): Thêm ArUco markers vào 4 góc phiếu
            aruco_size (float): Kích thước ArUco marker (đơn vị: cm)
        """
        self.title = title
        self.header_info = header_info or {}
        self.footer_text = footer_text or "Phiếu này chỉ có giá trị khi có chữ ký của Ban Kiểm phiếu"
        self.page_size = page_size
        self.add_aruco_markers = add_aruco_markers
        self.aruco_size = aruco_size * cm
        self.content_height = 0  # Sẽ được tính toán khi build
        
        # Cấu hình bảng mặc định
        self.columns = ["STT", "Họ và tên", "Chọn"]
        self.column_widths = [2*cm, 12*cm, 2*cm]
        self.table_style = None
        
        # Cấu hình font
        self._setup_fonts(font_path)
        
        # Styles
        self.styles = getSampleStyleSheet()
        self._setup_styles()
    
    def _setup_fonts(self, font_path=None):
        """Thiết lập font Unicode hỗ trợ tiếng Việt"""
        try:
            # Nếu có font_path tùy chỉnh
            if font_path and os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('CustomFont', font_path))
                self.font_name = 'CustomFont'
                return
            
            # Tìm font Times New Roman (hỗ trợ tiếng Việt tốt)
            possible_font_paths = [
                # Windows - Times New Roman
                'C:/Windows/Fonts/times.ttf',
                'C:/Windows/Fonts/timesbd.ttf',
                'C:/Windows/Fonts/Times New Roman.ttf',
                # Alternatives
                'C:/Windows/Fonts/Arial.ttf',
                'C:/Windows/Fonts/DejaVuSans.ttf',
                # Linux
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
                # macOS
                '/System/Library/Fonts/Supplemental/Times New Roman.ttf',
                '/Library/Fonts/Times New Roman.ttf',
            ]
            
            # Thử load các font có sẵn
            for font_file in possible_font_paths:
                if os.path.exists(font_file):
                    try:
                        font_name = os.path.basename(font_file).replace('.ttf', '')
                        if font_name not in pdfmetrics.getRegisteredFontNames():
                            pdfmetrics.registerFont(TTFont(font_name, font_file))
                        self.font_name = font_name
                        print(f"Đã load font: {font_name}")
                        return
                    except Exception as e:
                        continue
            
            # Fallback: Sử dụng Helvetica (không hỗ trợ tiếng Việt tốt)
            print("CẢNH BÁO: Không tìm thấy font Unicode. Tiếng Việt có thể hiển thị sai.")
            print("Khuyến nghị: Cài đặt font DejaVuSans hoặc truyền font_path khi khởi tạo.")
            self.font_name = 'Helvetica'
            
        except Exception as e:
            print(f"Lỗi khi thiết lập font: {e}")
            self.font_name = 'Helvetica'
    
    def _setup_styles(self):
        """Thiết lập các style cho văn bản"""
        # Style cho tiêu đề chính
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Title'],
            fontSize=16,
            fontName=self.font_name,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=colors.HexColor('#000000'),
            fontWeight='BOLD'
        )
        
        # Style cho thông tin header
        self.header_style = ParagraphStyle(
            'HeaderInfo',
            parent=self.styles['Normal'],
            fontSize=11,
            fontName=self.font_name,
            alignment=TA_LEFT,
            spaceAfter=6
        )
        
        # Style cho footer
        self.footer_style = ParagraphStyle(
            'Footer',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName=self.font_name,
            alignment=TA_CENTER,
            textColor=colors.grey
        )
    
    def set_table_config(self, columns, column_widths=None):
        """
        Cấu hình bảng dữ liệu
        
        Args:
            columns (list): Danh sách tên cột
            column_widths (list): Danh sách độ rộng các cột (đơn vị: cm hoặc mm)
        """
        self.columns = columns
        if column_widths:
            self.column_widths = column_widths
        else:
            # Tự động chia đều độ rộng
            available_width = self.page_size[0] - 4*cm
            col_width = available_width / len(columns)
            self.column_widths = [col_width] * len(columns)
    
    def set_table_style(self, custom_style):
        """
        Thiết lập style tùy chỉnh cho bảng
        
        Args:
            custom_style (TableStyle): Style tùy chỉnh cho bảng
        """
        self.table_style = custom_style
    
    def _get_default_table_style(self):
        """Trả về style mặc định cho bảng"""
        return TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), self.font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('FONTWEIGHT', (0, 0), (-1, 0), 'BOLD'),
            
            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ])
    
    def _create_header_section(self):
        """Tạo phần header với thông tin phiếu bầu"""
        elements = []
        
        # Tiêu đề chính
        title_para = Paragraph(f"<b>{self.title}</b>", self.title_style)
        elements.append(title_para)
        elements.append(Spacer(1, 0.3*cm))
        
        # Thông tin header
        if self.header_info:
            for key, value in self.header_info.items():
                info_text = f"<b>{key}:</b> {value}"
                info_para = Paragraph(info_text, self.header_style)
                elements.append(info_para)
        
        elements.append(Spacer(1, 0.5*cm))
        
        return elements
    
    def _create_table_section(self, data):
        """
        Tạo phần bảng dữ liệu
        
        Args:
            data (list): Dữ liệu bảng, mỗi hàng là một list
        """
        # Thêm header vào data
        table_data = [self.columns] + data
        
        # Tạo bảng
        table = Table(table_data, colWidths=self.column_widths, repeatRows=1)
        
        # Áp dụng style
        if self.table_style:
            table.setStyle(self.table_style)
        else:
            table.setStyle(self._get_default_table_style())
        
        return table
    
    def _create_footer_section(self):
        """Tạo phần footer"""
        elements = []
        
        elements.append(Spacer(1, 1*cm))
        
        # Chữ ký
        signature_text = """
        <para alignment="right">
        Ngày .... tháng .... năm .....<br/>
        <b>CHỮ KÝ CỦA CỬ TRI</b><br/>
        <br/>
        <br/>
        <br/>
        </para>
        """
        signature_para = Paragraph(signature_text, self.header_style)
        elements.append(signature_para)
        
        # Footer text
        if self.footer_text:
            footer_para = Paragraph(f"<i>{self.footer_text}</i>", self.footer_style)
            elements.append(footer_para)
        
        return elements
    
    def _generate_aruco_marker(self, marker_id, size_px=200):
        """
        Tạo ArUco marker image
        
        Args:
            marker_id (int): ID của marker (0-3 cho 4 góc)
            size_px (int): Kích thước marker tính bằng pixel
            
        Returns:
            str: Đường dẫn đến file ảnh marker tạm thời
        """
        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, size_px)
        
        # Lưu marker vào file tạm
        temp_path = f"temp_aruco_{marker_id}.png"
        cv2.imwrite(temp_path, marker_img)
        return temp_path
    
    def _add_aruco_markers_to_canvas(self, c, doc):
        """
        Thêm 4 ArUco markers vào 4 góc của nội dung phiếu bầu
        
        Args:
            c: Canvas object từ reportlab
            doc: Document object để lấy thông tin về nội dung
        """
        # Lấy kích thước trang và vùng nội dung
        page_width, page_height = self.page_size
        content_width = doc.width
        content_height = doc.height
        
        # Khoảng cách từ markers đến viền nội dung (0.3cm - gần hơn)
        offset = 0.3 * cm
        
        # Tính toán vị trí markers theo vùng nội dung
        # Vị trí bắt đầu của nội dung từ đáy trang
        content_start_y = page_height - doc.topMargin
        
        # Top markers: Đặt ở đầu vùng nội dung (phía trên)
        top_y = content_start_y + offset
        
        # Bottom markers: Tính từ top xuống theo chiều cao nội dung
        # Thay vì dùng bottomMargin, tính: top - content_height
        bottom_y = content_start_y - content_height - self.aruco_size - offset
        
        # Left markers: Đặt bên trái vùng nội dung
        left_x = doc.leftMargin - self.aruco_size - offset
        
        # Right markers: Đặt bên phải vùng nội dung
        right_x = doc.leftMargin + content_width + offset
        
        marker_positions = [
            (0, left_x, top_y),       # Marker 0: Top-left
            (1, right_x, top_y),      # Marker 1: Top-right  
            (2, right_x, bottom_y),   # Marker 2: Bottom-right
            (3, left_x, bottom_y)     # Marker 3: Bottom-left
        ]
        
        for marker_id, x_pos, y_pos in marker_positions:
            # Tạo marker image
            marker_path = self._generate_aruco_marker(marker_id, size_px=200)
            
            # Vẽ marker lên canvas
            c.drawImage(marker_path, x_pos, y_pos, 
                       width=self.aruco_size, height=self.aruco_size,
                       preserveAspectRatio=True, mask='auto')
            
            # Xóa file tạm
            try:
                os.remove(marker_path)
            except:
                pass
    
    def generate(self, data, output_path=None, add_logo=None):
        """
        Tạo file PDF phiếu bầu
        
        Args:
            data (list): Dữ liệu bảng (không bao gồm header)
            output_path (str): Đường dẫn lưu file. Nếu None, trả về BytesIO
            add_logo (str): Đường dẫn đến file logo (nếu có)
        
        Returns:
            BytesIO hoặc None: Buffer chứa PDF nếu output_path là None
        """
        # Tạo buffer hoặc file
        if output_path:
            pdf_file = output_path
        else:
            pdf_file = BytesIO()
        
        # Tạo document
        doc = SimpleDocTemplate(
            pdf_file,
            pagesize=self.page_size,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Tạo nội dung
        elements = []
        
        # Logo (nếu có)
        if add_logo and os.path.exists(add_logo):
            try:
                logo = Image(add_logo, width=3*cm, height=3*cm)
                logo.hAlign = 'CENTER'
                elements.append(logo)
                elements.append(Spacer(1, 0.3*cm))
            except Exception as e:
                print(f"Không thể thêm logo: {e}")
        
        # Header
        elements.extend(self._create_header_section())
        
        # Table
        table = self._create_table_section(data)
        elements.append(table)
        
        # Footer
        elements.extend(self._create_footer_section())
        
        # Build PDF
        if self.add_aruco_markers:
            # Nếu cần thêm ArUco markers, dùng custom canvas
            doc.build(elements, onFirstPage=self._add_markers_callback, 
                     onLaterPages=self._add_markers_callback)
        else:
            doc.build(elements)
        
        # Trả về buffer nếu không có output_path
        if not output_path:
            pdf_file.seek(0)
            return pdf_file
        
        return None
    
    def _add_markers_callback(self, canvas_obj, doc):
        """Callback để thêm ArUco markers vào mỗi trang"""
        self._add_aruco_markers_to_canvas(canvas_obj, doc)
    
    def generate_multiple_ballots(self, data, ballots_per_page=1, output_path=None):
        """
        Tạo nhiều phiếu bầu trên cùng một file PDF
        
        Args:
            data (list): Dữ liệu bảng cho các phiếu bầu
            ballots_per_page (int): Số phiếu trên mỗi trang
            output_path (str): Đường dẫn lưu file
        
        Returns:
            BytesIO hoặc None: Buffer chứa PDF nếu output_path là None
        """
        if output_path:
            pdf_file = output_path
        else:
            pdf_file = BytesIO()
        
        doc = SimpleDocTemplate(
            pdf_file,
            pagesize=self.page_size,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        elements = []
        
        for i in range(ballots_per_page):
            # Header
            elements.extend(self._create_header_section())
            
            # Table
            table = self._create_table_section(data)
            elements.append(table)
            
            # Footer
            elements.extend(self._create_footer_section())
            
            # Page break nếu không phải phiếu cuối
            if i < ballots_per_page - 1:
                elements.append(PageBreak())
        
        # Build PDF
        if self.add_aruco_markers:
            doc.build(elements, onFirstPage=self._add_markers_callback, 
                     onLaterPages=self._add_markers_callback)
        else:
            doc.build(elements)
        
        if not output_path:
            pdf_file.seek(0)
            return pdf_file
        
        return None


# Ví dụ sử dụng
def example_usage():
    """Ví dụ sử dụng BallotPDFGenerator"""
    
    # Tạo generator CÓ ArUco markers
    generator = BallotPDFGenerator(
        title="PHIẾU BẦU CỬ ĐẠI BIỂU QUỐC HỘI KHÓA XV",
        header_info={
            "Đơn vị bầu cử": "Trường Đại học ABC",
            "Kỳ bầu cử": "Năm 2024",
            "Ngày bầu cử": "15/12/2024",
            "Số phiếu": "BC-2024-001"
        },
        footer_text="Phiếu này chỉ có giá trị khi có đầy đủ chữ ký của Ban Kiểm phiếu và cử tri",
        add_aruco_markers=True,  # Thêm ArUco markers vào 4 góc
        aruco_size=1.0  # Kích thước marker 1.0cm
    )
    
    # Cấu hình bảng
    generator.set_table_config(
        columns=["STT", "Họ và tên ứng cử viên", "Năm sinh", "Đơn vị công tác", "Đánh dấu"],
        column_widths=[1.5*cm, 5*cm, 2*cm, 5*cm, 2*cm]
    )
    
    # Dữ liệu mẫu
    candidate_data = [
        ["1", "Nguyễn Văn A", "1980", "Khoa Công nghệ thông tin", "☐"],
        ["2", "Trần Thị B", "1985", "Khoa Kinh tế", "☐"],
        ["3", "Lê Văn C", "1978", "Khoa Kỹ thuật", "☐"],
        ["4", "Phạm Thị D", "1990", "Khoa Ngoại ngữ", "☐"],
        ["5", "Hoàng Văn E", "1982", "Khoa Y học", "☐"],
    ]
    
    # Tạo PDF với ArUco markers
    output_file = "phieu_bau_mau.pdf"
    generator.generate(candidate_data, output_path=output_file)
    print(f"Đã tạo phiếu bầu (có ArUco markers): {output_file}")
    
    # Hoặc lấy BytesIO để sử dụng trong Django response
    pdf_buffer = generator.generate(candidate_data)
    print(f"Đã tạo PDF buffer với {len(pdf_buffer.getvalue())} bytes")


if __name__ == "__main__":
    example_usage()
