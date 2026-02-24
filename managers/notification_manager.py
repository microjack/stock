import subprocess
import logging
from datetime import datetime
from plyer import notification
from models.config_model import Config
from models.state_model import State

class NotificationManager:
    """通知管理器"""
    
    @staticmethod
    def can_send_notification(config: Config, state: State) -> bool:
        """检查是否可以发送通知"""
        if state.last_notification_time is None:
            return True
        
        time_since_last = (datetime.now() - state.last_notification_time).total_seconds()
        return time_since_last >= config.notification_cooldown
    
    @staticmethod
    def send(title: str, message: str, critical: bool = False):
        """发送通知"""
        try:
            if critical:
                subprocess.run(
                    ['osascript', '-e', f'display alert "{title}" message "{message}" as critical'], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
            else:
                notification.notify(
                    title=title,
                    app_name='股票监控',
                    message=message,
                    timeout=10
                )
        except Exception as e:
            logging.error(f"发送通知失败: {str(e)}")