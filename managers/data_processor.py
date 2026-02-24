import logging
from typing import Dict, Any, Tuple, Optional
from models.config_model import Config
from models.state_model import State

class DataProcessor:
    """数据处理器"""
    
    @staticmethod
    def parse_data(data: Dict[str, Any]) -> Tuple[float, float, float, int]:
        """解析股票数据"""
        current_price = data['price']
        basic_price = data['last_close']
        difference_ratio = round((current_price - basic_price) / basic_price * 100, 2)
        amount = int(data['amount'] / 10000)  # 转换为万元
        return current_price, basic_price, difference_ratio, amount
    
    @staticmethod
    def check_volume_change(config: Config, state: State, 
                           amount: int, seconds: int) -> Optional[int]:
        """检查成交量变化"""
        # 每分钟开始时记录起始成交量
        if seconds == 0:
            state.start_amount = amount
            logging.debug("重置每分钟起始成交量")
            return None
        
        # 每分钟结束时检查成交量异常
        if seconds == 59 and state.start_amount > 0:
            volume_change = amount - state.start_amount
            if volume_change > config.volume_threshold:
                logging.warning(f"成交量异常增加: {volume_change}万")
                return volume_change
        
        return None
    
    @staticmethod
    def check_price_change(config: Config, difference_ratio: float) -> Tuple[bool, str]:
        """检查价格变化"""
        if abs(difference_ratio) > config.price_change_threshold:
            direction = "上涨" if difference_ratio > 0 else "下跌"
            logging.warning(f"价格大幅{direction}: {difference_ratio}%")
            return True, direction
        return False, ""