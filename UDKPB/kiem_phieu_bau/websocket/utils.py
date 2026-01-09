"""
WebSocket Utilities
Helper functions để gửi notifications qua WebSocket
"""
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification


def send_notification_to_user(user, poll, title, message, data=None):
    """
    Tạo notification và gửi real-time qua WebSocket cho user
    
    Args:
        user: User instance
        poll: Poll instance (có thể None)
        title: Tiêu đề thông báo
        message: Nội dung thông báo
        data: Dict chứa dữ liệu bổ sung (optional)
    
    Returns:
        Notification instance
    
    Example:
        from websocket.utils import send_notification_to_user
        
        send_notification_to_user(
            user=admin_user,
            poll=poll,
            title='Yêu cầu tham gia mới',
            message=f'{user.username} muốn tham gia {poll.title}',
            data={'member_id': member.member_id}
        )
    """
    # Tạo notification trong database
    notification = Notification.objects.create(
        user=user,
        poll=poll,
        title=title,
        message=message,
        data=data or {}
    )
    
    # Gửi real-time qua WebSocket (nếu user đang connect)
    try:
        channel_layer = get_channel_layer()
        user_group_name = f"user_{user.id}"
        
        async_to_sync(channel_layer.group_send)(
            user_group_name,
            {
                'type': 'notification_message',
                'data': notification.to_dict()
            }
        )
    except Exception as e:
        # Log error nhưng không fail (user có thể offline)
        print(f"[WebSocket] Failed to send notification to user {user.id}: {e}")
    
    return notification


def send_notification_to_poll_managers(poll, title, message, data=None):
    """
    Gửi notification cho tất cả managers của poll
    
    Args:
        poll: Poll instance
        title: Tiêu đề
        message: Nội dung
        data: Dict bổ sung (optional)
    
    Returns:
        List of created Notification instances
    
    Example:
        from websocket.utils import send_notification_to_poll_managers
        
        send_notification_to_poll_managers(
            poll=poll,
            title='Yêu cầu tham gia mới',
            message=f'{user.username} muốn tham gia',
            data={'member_id': member.member_id}
        )
    """
    from poll.models import PollMember
    
    notifications = []
    
    # Lấy danh sách managers (người tạo poll + members có role='manager')
    managers = []
    
    # Thêm người tạo poll
    if poll.created_by:
        managers.append(poll.created_by)
    
    # Thêm các members có role='manager' và status='active'
    manager_members = PollMember.objects.filter(
        poll=poll,
        role='manager',
        status='active'
    ).select_related('account')
    
    for member in manager_members:
        if member.account not in managers:
            managers.append(member.account)
    
    # Gửi notification cho từng manager
    for manager in managers:
        notification = send_notification_to_user(
            user=manager,
            poll=poll,
            title=title,
            message=message,
            data=data
        )
        notifications.append(notification)
    
    return notifications


def broadcast_to_poll_members(poll, title, message, data=None):
    """
    Broadcast notification cho TẤT CẢ members active của poll
    
    Args:
        poll: Poll instance
        title: Tiêu đề
        message: Nội dung
        data: Dict bổ sung (optional)
    
    Returns:
        List of created Notification instances
    
    Example:
        from websocket.utils import broadcast_to_poll_members
        
        broadcast_to_poll_members(
            poll=poll,
            title='Kiểm phiếu hoàn tất',
            message=f'Cuộc bỏ phiếu {poll.title} đã hoàn tất kiểm phiếu',
            data={'total_ballots': 100}
        )
    """
    from poll.models import PollMember
    
    notifications = []
    
    # Lấy tất cả members active
    members = PollMember.objects.filter(
        poll=poll,
        status='active'
    ).select_related('account')
    
    # Thêm người tạo poll (nếu chưa là member)
    users = set([member.account for member in members])
    if poll.created_by and poll.created_by not in users:
        users.add(poll.created_by)
    
    # Gửi notification cho từng user
    for user in users:
        notification = send_notification_to_user(
            user=user,
            poll=poll,
            title=title,
            message=message,
            data=data
        )
        notifications.append(notification)
    
    return notifications


def get_unread_count(user):
    """
    Đếm số notification chưa đọc của user
    
    Args:
        user: User instance
    
    Returns:
        int: số lượng notification chưa đọc
    
    Example:
        from websocket.utils import get_unread_count
        
        count = get_unread_count(request.user)
    """
    return Notification.objects.filter(user=user, is_read=False).count()


def mark_all_as_read(user):
    """
    Đánh dấu tất cả notification của user là đã đọc
    
    Args:
        user: User instance
    
    Returns:
        int: số lượng notification đã được đánh dấu
    
    Example:
        from websocket.utils import mark_all_as_read
        
        count = mark_all_as_read(request.user)
    """
    return Notification.objects.filter(user=user, is_read=False).update(is_read=True)
