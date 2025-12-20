from django.db import models
from django.conf import settings
from poll.models import Poll

# Create your models here.

def ballot_pdf_upload_path(instance, filename):
    """Generate upload path for ballot PDF files"""
    if instance.poll:
        return f'form_ballot_pdfs/{instance.poll.poll_id}/{filename}'
    return f'form_ballot_pdfs/unassigned/{filename}'

class BallotDocument(models.Model):
    """Model to store Ballot document configurations"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, null=True, blank=True, related_name='ballot_documents')  # Thuộc cuộc bỏ phiếu
    title = models.CharField(max_length=255, default="Untitled Document")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Margin settings
    margin_top = models.FloatField(default=2.0)
    margin_bottom = models.FloatField(default=2.0)
    margin_left = models.FloatField(default=2.0)
    margin_right = models.FloatField(default=2.0)
    
    # Marker distances (khoảng cách giữa 2 biên lề, tính bằng cm)
    marker_distance_horizontal = models.FloatField(null=True, blank=True, help_text="Khoảng cách ngang giữa 2 biên lề (cm)")
    marker_distance_vertical = models.FloatField(null=True, blank=True, help_text="Khoảng cách dọc giữa 2 biên lề (cm)")
    
    # General settings
    font_family = models.CharField(max_length=50, default="Arial")
    font_size = models.IntegerField(default=12)
    
    # Content as JSON
    header_content = models.JSONField(default=dict, blank=True)  # Quốc hiệu tiêu ngữ
    title_content = models.JSONField(default=dict, blank=True)   # Phần tiêu đề
    body_content = models.JSONField(default=list, blank=True)    # Phần nội dung
    footer_content = models.JSONField(default=list, blank=True)  # Ghi chú, chân trang
    
    # Generated PDF path
    pdf_file = models.FileField(upload_to=ballot_pdf_upload_path, null=True, blank=True)
    
    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%Y-%m-%d')}"
    
    def get_body_tables_info(self):
        """
        Lấy thông tin số hàng và số cột của các bảng trong body_content
        
        Returns:
            list: Danh sách dict chứa thông tin các bảng:
                [
                    {
                        'row_index': 0,  # Vị trí row trong body_content (0-based)
                        'row_id': 1,     # ID của row
                        'type': 'table', # Loại: 'table' hoặc 'table-double'
                        'num_cols': 3,   # Số cột
                        'num_rows': 5,   # Số hàng (nested rows)
                        'margin': 0      # Lề
                    },
                    ...
                ]
        """
        tables_info = []
        
        if not isinstance(self.body_content, list):
            return tables_info
        
        for idx, row in enumerate(self.body_content):
            if not isinstance(row, dict):
                continue
                
            row_type = row.get('type', '')
            
            # Chỉ xử lý các type là table
            if row_type in ['table', 'table-double']:
                nested_rows = row.get('nestedRows', [])
                num_cols = row.get('numCols', 0)
                num_rows = len(nested_rows) if isinstance(nested_rows, list) else 0
                
                table_info = {
                    'row_index': idx,
                    'row_id': row.get('id'),
                    'type': row_type,
                    'num_cols': num_cols,
                    'num_rows': num_rows,
                    'margin': row.get('margin', 0),
                    'double_mode': row.get('doubleMode') if row_type == 'table-double' else None
                }
                
                tables_info.append(table_info)
        
        return tables_info
    
    def get_first_table_dimensions(self):
        """
        Lấy số hàng và số cột của bảng đầu tiên trong body_content
        
        Returns:
            tuple: (num_rows, num_cols) hoặc (None, None) nếu không có bảng
        """
        tables = self.get_body_tables_info()
        
        if tables:
            first_table = tables[0]
            return (first_table['num_rows'], first_table['num_cols'])
        
        return (None, None)
    
    class Meta:
        ordering = ['-updated_at']
