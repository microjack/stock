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
from typing import Dict, List, Tuple, Optional, Any
from pytdx.hq import TdxHq_API
from plyer import notification

# ==================================================
# 配置
# ==================================================

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 通用配置
CONFIG = {
    'host': '111.229.247.189',
    'port': 7709,
    'trading_ranges': [
        ("09:30", "11:30"),
        ("13:00", "15:00")
    ],
    'check_interval': 1,
    'max_retries': 3,
    'retry_delay': 5,
    'notification_cooldown': 60,
}

# ====================================================
# 股票配置
# ====================================================

# 初始化股票配置列表
STOCKS_CONFIG = []

STOCKS_CONFIG.append({
    "symbol": "机科股份",
    "code": "920579",
    "market_code": 2,
    "enabled": True,
    "volume_threshold": 50,
    "price_alert_threshold": 2.0,
    "price_change_threshold": 3.0,
    "target_prices": [24.0, 24.5, 25.0]
})

STOCKS_CONFIG.append({
    "symbol": "埃斯顿",
    "code": "002747",
    "market_code": 0,
    "enabled": True,
    "volume_threshold": 500,
    "price_alert_threshold": 2.0,
    "price_change_threshold": 3.0,
    "target_prices": [24.0, 24.5, 25.0]
})

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
        self.last_notification_time = None
        self.start_amount = 0
        self.last_minute = -1
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

def is_trading_hours() -> bool:
    """检查是否在交易时间内"""
    current_time = datetime.now().strftime("%H:%M")
    for start, end in CONFIG['trading_ranges']:
        if start <= current_time <= end:
            return True
    return False

def check_network_connection() -> bool:
    """检查网络连接"""
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except:
        return False

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

def can_send_notification(stock: Stock) -> bool:
    """检查是否可以发送通知"""
    if stock.last_notification_time is None:
        return True
    
    time_since_last = (datetime.now() - stock.last_notification_time).total_seconds()
    return time_since_last >= CONFIG['notification_cooldown']

def send_notification(stock: Stock, title: str, message: str, critical: bool = False):
    """发送通知"""
    if not can_send_notification(stock):
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
                app_name='股票监控',
                message=message,
                timeout=10
            )
        
        stock.last_notification_time = datetime.now()
        logger.info(f"已发送通知: {full_title} - {message}")
        
    except Exception as e:
        logger.error(f"发送通知失败: {str(e)}")

def check_stock_alerts(stock: Stock, current_time: datetime):
    """检查股票警报"""
    current_minute = current_time.minute
    current_second = current_time.second
    
    # 每分钟开始时记录起始成交量
    if current_second == 0 and current_minute != stock.last_minute:
        stock.start_amount = stock.amount
        stock.last_minute = current_minute
        logger.debug(f"{stock.symbol} 重置每分钟起始成交量: {stock.amount:.2f}万")
    
    # 每分钟结束前检查成交量异常（使用时间范围，提高容错性）
    if 58 <= current_second <= 59 and stock.start_amount > 0:
        volume_change = stock.amount - stock.start_amount
        if volume_change > stock.volume_threshold:
            logger.warning(f"{stock.symbol} 成交量异常增加: {volume_change:.2f}万")
            send_notification(
                stock, 
                "成交量提醒", 
                f"成交量增加 {volume_change:.2f}万"
            )
            stock.start_amount = stock.amount

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
    
    try:
        while True:
            # 检查是否在交易时间
            if not is_trading_hours():
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
                response = api.get_security_quotes(enabled_stocks)
                
                if not response:
                    logger.warning("获取股票数据为空，可能连接已断开")
                    api.disconnect()
                    is_connected = False
                    continue
                
                # 更新股票数据
                current_time = datetime.now()
                
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
                                f"股票: {stock.symbol}({stock.code}) | "
                                f"价格: {stock.current_price:.2f} | "
                                f"涨跌幅: {stock.change_percent:+.2f}% | "
                                f"成交额: {stock.amount:.2f}万"
                            )
                
            except Exception as e:
                logger.error(f"获取股票数据失败: {str(e)}")
                api.disconnect()
                is_connected = False
            
            time.sleep(CONFIG['check_interval'])
            
    except KeyboardInterrupt:
        logger.info("用户中断监控")
    except Exception as e:
        logger.error(f"监控过程中发生错误: {str(e)}")
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
