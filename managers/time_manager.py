from datetime import datetime
from typing import Tuple
from models.config_model import Config

class TimeManager:
    """时间管理器"""
    
    @staticmethod
    def is_trading_hours(config: Config) -> bool:
        """检查是否在交易时间内"""
        current_time = datetime.now().strftime("%H:%M")
        for start, end in config.trading_ranges:
            if start <= current_time <= end:
                return True
        return False
    
    @staticmethod
    def get_time_info() -> Tuple[str, int]:
        """获取当前时间信息"""
        current_time = datetime.now()
        time_str = current_time.strftime("%H:%M:%S")
        seconds = current_time.second
        return time_str, seconds