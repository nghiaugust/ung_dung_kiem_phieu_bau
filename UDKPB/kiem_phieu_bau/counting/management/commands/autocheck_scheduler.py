"""
Management command để kiểm soát Auto Check Scheduler
Usage:
    python manage.py autocheck_scheduler --status    # Xem trạng thái
    python manage.py autocheck_scheduler --start     # Khởi động thủ công
    python manage.py autocheck_scheduler --stop      # Dừng scheduler
"""
from django.core.management.base import BaseCommand
from counting.auto_check_scheduler import get_scheduler, start_scheduler, stop_scheduler


class Command(BaseCommand):
    help = 'Quản lý Auto Check Scheduler'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            action='store_true',
            help='Xem trạng thái scheduler'
        )
        parser.add_argument(
            '--start',
            action='store_true',
            help='Khởi động scheduler'
        )
        parser.add_argument(
            '--stop',
            action='store_true',
            help='Dừng scheduler'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=15,
            help='Interval (giây) giữa các lần quét (mặc định: 15)'
        )
    
    def handle(self, *args, **options):
        if options['status']:
            self.show_status()
        elif options['start']:
            self.start_scheduler(options['interval'])
        elif options['stop']:
            self.stop_scheduler()
        else:
            self.stdout.write(
                self.style.WARNING('Vui lòng chọn một option: --status, --start, hoặc --stop')
            )
    
    def show_status(self):
        """Hiển thị trạng thái scheduler"""
        scheduler = get_scheduler()
        
        if scheduler is None:
            self.stdout.write(
                self.style.WARNING('Scheduler chưa được khởi tạo')
            )
        elif scheduler.running:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Scheduler đang chạy (interval: {scheduler.interval}s)')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Scheduler đã dừng (interval: {scheduler.interval}s)')
            )
    
    def start_scheduler(self, interval):
        """Khởi động scheduler"""
        scheduler = start_scheduler(interval=interval)
        
        if scheduler.running:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Scheduler đã được khởi động (interval: {interval}s)')
            )
        else:
            self.stdout.write(
                self.style.ERROR('✗ Không thể khởi động scheduler')
            )
    
    def stop_scheduler(self):
        """Dừng scheduler"""
        scheduler = get_scheduler()
        
        if scheduler is None:
            self.stdout.write(
                self.style.WARNING('Scheduler chưa được khởi tạo')
            )
            return
        
        stop_scheduler()
        self.stdout.write(
            self.style.SUCCESS('✓ Scheduler đã được dừng')
        )
