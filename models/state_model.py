from datetime import datetime
from typing import Optional

class State:
    """状态管理类"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """重置状态"""
        self.last_notification_time: Optional[datetime] = None
        self.start_amount: int = 0
        self.last_price: Optional[float] = None
        self.connection_retries: int = 0
        self.network_retries: int = 0
        self.last_successful_check: Optional[datetime] = None
        self.is_connected: bool = False
    
    def update_successful_check(self):
        """更新最后成功检查时间"""
        self.last_successful_check = datetime.now()