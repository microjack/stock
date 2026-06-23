"""
股票监控程序 - 单文件简化版
支持多股票监控，配置简单，易于运行
"""

import time
import logging
import json
import subprocess
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from pytdx.hq import TdxHq_API
from plyer import notification

# ==================================================
# 配置
# ==================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    'host': '111.229.247.189',
    'port': 7709,
    'log_path': str(BASE_DIR / 'monitor.log'),
    'trading_ranges': [
        ("09:30", "11:30"),
        ("13:00", "15:00")
    ],
    'check_interval': 1,
    'max_retries': 3,
    'retry_delay': 5,
    'notification_cooldown': 60,
    'closing_snapshot_grace_seconds': 10,
}

DEFAULT_STOCKS_CONFIG = [{
    "symbol": "国匠精工",
    "code": "920579",
    "market_code": 2,
    "enabled": True,
    "volume_threshold": 200,
    "price_alert_threshold": 7.0,
    "price_change_threshold": 30.0,
    "target_prices": [21]
}, {
    "symbol": "无敌小强",
    "code": "688608",
    "market_code": 1,
    "enabled": True,
    "volume_threshold": 2000,
    "price_alert_threshold": 7.0,
    "price_change_threshold": 20.0,
    "target_prices": [220]
}, {
    "symbol": "疯狂石头",
    "code": "688169",
    "market_code": 1,
    "enabled": True,
    "volume_threshold": 2000,
    "price_alert_threshold": 7.0,
    "price_change_threshold": 20.0,
    "target_prices": [150]
}]

def load_app_config(config_path: Path = CONFIG_PATH) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """加载配置文件，失败时回退到默认配置。"""
    config = DEFAULT_CONFIG.copy()
    stocks_config = [stock.copy() for stock in DEFAULT_STOCKS_CONFIG]
    warnings = []

    if not config_path.exists():
        warnings.append(f"配置文件不存在，使用默认配置: {config_path}")
        return config, stocks_config, warnings

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            file_config = json.load(config_file)
    except (OSError, json.JSONDecodeError) as e:
        warnings.append(f"读取配置文件失败，使用默认配置: {e}")
        return config, stocks_config, warnings

    loaded_config = file_config.get("config", {})
    if isinstance(loaded_config, dict):
        config.update(loaded_config)
    else:
        warnings.append("config 字段不是对象，已使用默认通用配置")

    loaded_stocks = file_config.get("stocks")
    if isinstance(loaded_stocks, list):
        stocks_config = loaded_stocks
    elif loaded_stocks is not None:
        warnings.append("stocks 字段不是数组，已使用默认股票配置")

    return config, stocks_config, warnings

def parse_trading_ranges(ranges: List[List[str]]) -> List[Tuple[Any, Any]]:
    """解析交易时间段，结束时间按开区间处理。"""
    return [
        (
            datetime.strptime(start, "%H:%M").time(),
            datetime.strptime(end, "%H:%M").time()
        )
        for start, end in ranges
    ]

CONFIG, STOCKS_CONFIG, CONFIG_WARNINGS = load_app_config()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG['log_path']),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

for warning in CONFIG_WARNINGS:
    logger.warning(warning)

TRADING_RANGES = parse_trading_ranges(CONFIG['trading_ranges'])

# ==================================================
# 股票数据类
# ==================================================

class Stock:
    """股票类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.symbol = config.get('symbol', '')
        self.code = config.get('code', '')
        self.market_code = config.get('market_code', 0)
        self.enabled = config.get('enabled', True)
        
        # 监控规则
        self.volume_threshold = config.get('volume_threshold', 10)
        self.price_alert_threshold = config.get('price_alert_threshold', 1.0)
        self.price_change_threshold = config.get('price_change_threshold', 3.0)
        
        # 到价提醒配置
        self.target_prices = config.get('target_prices', [])
        self.target_triggered = {}  # 记录每个目标价是否已触发
        
        # 初始化目标价触发状态
        for price in self.target_prices:
            self.target_triggered[price] = False
        
        # 状态
        self.current_price = 0.0
        self.last_close = 0.0
        self.volume = 0
        self.amount = 0.0
        self.change_percent = 0.0
        
        # 监控状态
        self.last_notification_times = {}
        self.start_amount = 0
        self.last_amount_minute = None
        self.last_update = None
        
    def update(self, data: Dict[str, Any]):
        """更新股票数据"""
        self.current_price = data.get('price', 0.0)
        self.last_close = data.get('last_close', 0.0)
        self.volume = data.get('vol', 0)
        self.amount = data.get('amount', 0.0) / 10000  # 转换为万元
        
        if self.last_close > 0:
            self.change_percent = round((self.current_price - self.last_close) / self.last_close * 100, 2)
        
        self.last_update = datetime.now()

# ==================================================
# 工具函数
# ==================================================

def is_trading_hours(now: Optional[datetime] = None) -> bool:
    """检查是否在交易时间内"""
    current_time = (now or datetime.now()).time()
    for start, end in TRADING_RANGES:
        if start <= current_time < end:
            return True
    return False

def get_closing_snapshot_key(now: Optional[datetime] = None) -> Optional[str]:
    """在收盘后的短窗口内返回快照标识，确保 11:30/15:00 数据被抓取一次。"""
    current = now or datetime.now()
    grace_seconds = CONFIG.get('closing_snapshot_grace_seconds', 10)

    for _, end in TRADING_RANGES:
        session_end = current.replace(
            hour=end.hour,
            minute=end.minute,
            second=end.second,
            microsecond=0
        )
        elapsed_seconds = (current - session_end).total_seconds()
        if 0 <= elapsed_seconds <= grace_seconds:
            return f"{current.date()} {end.strftime('%H:%M')}"

    return None

def check_network_connection() -> bool:
    """检查网络连接"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect(("8.8.8.8", 53))
        return True
    except OSError:
        return False
    finally:
        sock.close()

def wait_for_network_recovery(max_retries: int = 5) -> bool:
    """等待网络恢复"""
    retry_count = 0
    while retry_count < max_retries:
        if check_network_connection():
            logger.info("网络连接已恢复")
            return True
        
        retry_count += 1
        wait_time = 5 * (2 ** (retry_count - 1))
        logger.warning(f"网络连接失败，第{retry_count}次重试，等待{wait_time}秒...")
        time.sleep(wait_time)
    
    logger.error("网络连接失败超过最大重试次数")
    return False

def can_send_notification(stock: Stock, title: str) -> bool:
    """检查是否可以发送通知"""
    last_notification_time = stock.last_notification_times.get(title)
    if last_notification_time is None:
        return True
    
    time_since_last = (datetime.now() - last_notification_time).total_seconds()
    return time_since_last >= CONFIG['notification_cooldown']

def send_notification(stock: Stock, title: str, message: str, critical: bool = False):
    """发送通知"""
    if not can_send_notification(stock, title):
        return
    
    try:
        full_title = f"[{stock.symbol}] {title}"
        
        if critical:
            subprocess.run(
                ['osascript', '-e', f'display alert "{full_title}" message "{message}" as critical'], 
                capture_output=True, 
                text=True, 
                check=True
            )
        else:
            notification.notify(
                title=full_title,
                app_name=f"价格: {stock.current_price:.2f}",
                message=message,
                timeout=10
            )
        
        stock.last_notification_times[title] = datetime.now()
        logger.info(f"已发送通知: {full_title} - {message}")
        
    except Exception as e:
        logger.error(f"发送通知失败: {str(e)}")

def send_system_notification(title: str, message: str, critical: bool = False):
    """发送程序级通知"""
    try:
        full_title = f"[股票监控] {title}"

        if critical:
            subprocess.run(
                ['osascript', '-e', f'display alert "{full_title}" message "{message}" as critical'],
                capture_output=True,
                text=True,
                check=True
            )
        else:
            notification.notify(
                title=full_title,
                app_name="股票监控",
                message=message,
                timeout=10
            )

        logger.info(f"已发送系统通知: {full_title} - {message}")

    except Exception as e:
        logger.error(f"发送系统通知失败: {str(e)}")

def check_stock_alerts(stock: Stock, current_time: datetime):
    """检查股票警报"""
    current_minute = current_time.replace(second=0, microsecond=0)
    
    # 按分钟边界结算成交额变化，避免因为循环错过固定秒数而漏报。
    if stock.last_amount_minute is None:
        stock.start_amount = stock.amount
        stock.last_amount_minute = current_minute
    elif current_minute != stock.last_amount_minute:
        elapsed_minutes = (current_minute - stock.last_amount_minute).total_seconds() / 60
        if elapsed_minutes > 1:
            stock.start_amount = stock.amount
            stock.last_amount_minute = current_minute
            logger.debug(f"{stock.symbol} 成交额基准已重置: {stock.amount:.2f}万")
        else:
            volume_change = stock.amount - stock.start_amount
            if volume_change > stock.volume_threshold:
                logger.warning(f"{stock.symbol} 成交量异常变化: {volume_change:.2f}万")
                send_notification(
                    stock,
                    "成交量提醒",
                    f"成交额: {volume_change:.2f}万"
                )

            stock.start_amount = stock.amount
            stock.last_amount_minute = current_minute

    # 检查价格提醒
    if abs(stock.change_percent) > stock.price_alert_threshold:
        direction = "上涨" if stock.change_percent > 0 else "下跌"
        send_notification(
            stock,
            "价格提醒",
            f"{direction}{abs(stock.change_percent)}%"
        )
    
    # 检查价格大幅波动
    if abs(stock.change_percent) > stock.price_change_threshold:
        direction = "上涨" if stock.change_percent > 0 else "下跌"
        logger.warning(f"{stock.symbol} 价格大幅{direction}: {stock.change_percent}%")
        send_notification(
            stock,
            "价格波动警告",
            f"{direction}{abs(stock.change_percent)}%",
            critical=True
        )
    
    # 检查到价提醒（多个目标价）
    for target_price in stock.target_prices:
        if not stock.target_triggered[target_price] and stock.current_price >= target_price:
            stock.target_triggered[target_price] = True
            logger.warning(f"{stock.symbol} 达到目标价: {stock.current_price:.2f} >= {target_price}")
            send_notification(
                stock,
                "到价提醒",
                f"达到目标价 {target_price:.2f}，当前价 {stock.current_price:.2f}",
                critical=True
            )

# ==================================================
# 主监控函数
# ==================================================

def fetch_and_process_quotes(
    api: TdxHq_API,
    stocks: Dict[str, Stock],
    enabled_stocks: List[Tuple[int, str]],
    snapshot_label: Optional[str] = None
) -> bool:
    """获取行情、更新状态、检查提醒并写入日志。"""
    response = api.get_security_quotes(enabled_stocks)

    if not response:
        logger.warning("获取股票数据为空，可能连接已断开")
        return False

    current_time = datetime.now()
    log_prefix = f"{snapshot_label} | " if snapshot_label else ""

    for item in response:
        if isinstance(item, dict) and 'code' in item:
            code = item['code']
            if code in stocks:
                stock = stocks[code]
                stock.update(item)

                # 检查警报
                check_stock_alerts(stock, current_time)

                # 记录日志
                logger.info(
                    f"{log_prefix}股票: {stock.symbol}({stock.code}) | "
                    f"价格: {stock.current_price:.2f} | "
                    f"涨跌幅: {stock.change_percent:+.2f}% | "
                    f"成交额: {stock.amount:.2f}万"
                )

    return True

def monitor_stocks():
    """监控多支股票"""
    # 创建股票对象
    stocks = {}
    enabled_stocks = []
    
    for stock_config in STOCKS_CONFIG:
        stock = Stock(stock_config)
        stocks[stock.code] = stock
        
        if stock.enabled:
            enabled_stocks.append((stock.market_code, stock.code))
    
    logger.info(f"开始监控 {len(enabled_stocks)} 支股票")
    
    # 连接TDX
    api = TdxHq_API()
    is_connected = False
    completed_closing_snapshots = set()
    
    try:
        while True:
            current_time = datetime.now()
            # 检查是否在交易时间
            if not is_trading_hours(current_time):
                snapshot_key = get_closing_snapshot_key(current_time)
                if snapshot_key and snapshot_key not in completed_closing_snapshots:
                    if not check_network_connection():
                        logger.warning("网络连接异常")
                        if not wait_for_network_recovery():
                            logger.error("网络连接失败，退出程序")
                            break
                        continue

                    if not is_connected:
                        if not api.connect(CONFIG['host'], CONFIG['port']):
                            logger.warning("连接TDX服务器失败，5秒后重试...")
                            time.sleep(5)
                            continue

                        is_connected = True
                        logger.info("成功连接TDX服务器")

                    try:
                        snapshot_time = snapshot_key.split()[-1]
                        if fetch_and_process_quotes(
                            api,
                            stocks,
                            enabled_stocks,
                            snapshot_label=f"收盘快照({snapshot_time})"
                        ):
                            completed_closing_snapshots.add(snapshot_key)
                        else:
                            api.disconnect()
                            is_connected = False
                    except Exception as e:
                        logger.error(f"获取收盘快照失败: {str(e)}")
                        api.disconnect()
                        is_connected = False

                    time.sleep(CONFIG['check_interval'])
                    continue

                logger.info("当前非交易时间，等待60秒后重试")
                
                if is_connected:
                    api.disconnect()
                    is_connected = False
                
                time.sleep(60)
                continue
            
            # 检查网络连接
            if not check_network_connection():
                logger.warning("网络连接异常")
                if not wait_for_network_recovery():
                    logger.error("网络连接失败，退出程序")
                    break
                continue
            
            # 连接TDX服务器
            if not is_connected:
                if not api.connect(CONFIG['host'], CONFIG['port']):
                    logger.warning("连接TDX服务器失败，5秒后重试...")
                    time.sleep(5)
                    continue
                
                is_connected = True
                logger.info("成功连接TDX服务器")
            
            # 获取股票数据
            try:
                if not fetch_and_process_quotes(api, stocks, enabled_stocks):
                    api.disconnect()
                    is_connected = False
                    continue

            except Exception as e:
                logger.error(f"获取股票数据失败: {str(e)}")
                api.disconnect()
                is_connected = False
            
            time.sleep(CONFIG['check_interval'])
            
    except KeyboardInterrupt:
        logger.info("用户中断监控")
    except Exception as e:
        logger.error(f"监控过程中发生错误: {str(e)}")
        send_system_notification(
            "监控程序异常",
            f"{str(e)}",
            critical=True
        )
    finally:
        if is_connected:
            api.disconnect()
        logger.info("股票监控程序结束")

# ==================================================
# 主程序
# ==================================================

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("股票监控程序启动")
    logger.info("=" * 50)
    
    monitor_stocks()
