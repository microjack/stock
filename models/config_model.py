from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Config:
    """配置数据类"""
    host: str
    port: int
    market_code: int
    stock_code: str
    trading_ranges: List[Tuple[str, str]]
    check_interval: int
    max_retries: int
    retry_delay: int
    network_check_interval: int
    max_network_retries: int
    network_retry_delay: int
    volume_threshold: int
    price_change_threshold: float
    notification_cooldown: int