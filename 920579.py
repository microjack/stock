import time
import logging
import subprocess
from datetime import datetime
from pytdx.hq import TdxHq_API
from plyer import notification

# ==================================================
# 日志配置
# ==================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("stock_monitor.log"),  # 日志文件
        logging.StreamHandler()                    # 控制台输出
    ]
)

# ==================================================
# 配置参数
# ==================================================
CONFIG = {
    'host': '111.229.247.189',       # TDX服务器地址
    'port': 7709,                    # TDX服务器端口
    'market_code': 2,                # 市场代码（北交所）
    'stock_code': "920579",          # 股票代码（机科股份）
    'trading_ranges': [              # 交易时间段
        ("09:30", "11:30"),
        ("13:00", "15:00")
    ],
    'check_interval': 1,             # 数据检查间隔(秒)
    'max_retries': 3,                # 最大连接重试次数
    'retry_delay': 5,                # 重试延迟(秒)
    'volume_threshold': 100,         # 成交量异常阈值(万)
    'price_change_threshold': 5.0,   # 涨跌幅异常阈值(%)
    'notification_cooldown': 60,     # 通知冷却时间(秒)
}

# ==================================================
# 全局状态管理
# ==================================================
state = {
    'last_notification_time': None,  # 上次通知时间
    'start_amount': 0,               # 每分钟起始成交量
    'last_price': None,              # 上次记录的价格
    'connection_retries': 0          # 连接重试次数
}

# ==================================================
# 功能函数
# ==================================================

def is_trading_hours():
    """
    检查当前是否在交易时间内
    
    Returns:
        bool: True表示在交易时间内，False表示非交易时间
    """
    current_time = datetime.now().strftime("%H:%M")
    for start, end in CONFIG['trading_ranges']:
        if start <= current_time <= end:
            return True
    return False

def send_notification(title, message, critical=False):
    """
    发送系统通知
    
    Args:
        title (str): 通知标题
        message (str): 通知内容
        critical (bool): 是否为关键通知（使用不同样式）
    """
    # 检查通知冷却时间
    current_time = datetime.now()
    if (state['last_notification_time'] and 
        (current_time - state['last_notification_time']).total_seconds() < CONFIG['notification_cooldown']):
        return
    
    try:
        if critical:
            # macOS系统关键通知
            subprocess.run(
                ['osascript', '-e', f'display alert "{title}" message "{message}" as critical'], 
                capture_output=True, 
                text=True, 
                check=True
            )
        else:
            # 跨平台普通通知
            notification.notify(
                title=title,
                app_name='股票监控',
                message=message,
                timeout=10
            )
        
        # 更新最后通知时间
        state['last_notification_time'] = current_time
        logging.info(f"已发送通知: {title} - {message}")
    except Exception as e:
        logging.error(f"发送通知失败: {str(e)}")

def process_stock_data(data):
    """
    处理股票数据并触发相应操作
    
    Args:
        data (dict): 股票数据字典
    """
    # 解析关键数据
    current_price = data['price']
    basic_price = data['last_close']
    difference_ratio = round((current_price - basic_price) / basic_price * 100, 2)
    amount = int(data['amount'] / 10000)  # 转换为万元
    
    current_time = datetime.now()
    seconds = current_time.second
    
    # 每分钟开始时记录起始成交量
    if seconds == 0:
        state['start_amount'] = amount
        logging.debug("重置每分钟起始成交量")
    
    # 每分钟结束时检查成交量异常
    if seconds == 59 and state['start_amount'] > 0:
        volume_change = amount - state['start_amount']
        if volume_change > CONFIG['volume_threshold']:
            logging.warning(f"成交量异常增加: {volume_change}万")
            send_notification(
                "成交量提醒", 
                f"{CONFIG['stock_code']} 成交量增加 {volume_change}万"
            )
    
    # 检查价格大幅波动
    if abs(difference_ratio) > CONFIG['price_change_threshold']:
        direction = "上涨" if difference_ratio > 0 else "下跌"
        logging.warning(f"价格大幅{direction}: {difference_ratio}%")
        send_notification(
            "价格波动警告", 
            f"{CONFIG['stock_code']} {direction}{abs(difference_ratio)}%", 
            critical=True
        )
    
    # 记录常规数据
    logging.info(
        f"时间: {current_time.strftime('%H:%M:%S')} | "
        f"价格: {current_price} | "
        f"涨跌幅: {difference_ratio}% | "
        f"成交量: {amount}万"
    )
    
    # 保存当前价格用于下次比较
    state['last_price'] = current_price

# ==================================================
# 主监控函数
# ==================================================

def monitor_stock():
    """
    主监控函数，负责连接API并持续监控股票数据
    """
    api = TdxHq_API()
    logging.info("股票监控程序启动")
    
    try:
        while True:
            # 检查是否在交易时间
            if not is_trading_hours():
                logging.info("当前非交易时间，等待60秒后重试")
                time.sleep(60)
                continue
                
            # 尝试连接API
            if not api.connect(CONFIG['host'], CONFIG['port']):
                state['connection_retries'] += 1
                
                # 超过最大重试次数则退出
                if state['connection_retries'] > CONFIG['max_retries']:
                    logging.error("连接失败次数过多，退出程序")
                    return
                
                logging.warning(f"连接失败({state['connection_retries']}/{CONFIG['max_retries']})，"
                               f"{CONFIG['retry_delay']}秒后重试...")
                time.sleep(CONFIG['retry_delay'])
                continue
            
            # 连接成功，重置重试计数器
            state['connection_retries'] = 0
            logging.info("成功连接TDX服务器")
            
            # 主监控循环
            while is_trading_hours():
                try:
                    # 获取股票数据
                    response = api.get_security_quotes([(CONFIG['market_code'], CONFIG['stock_code'])])
                    
                    if response:
                        process_stock_data(response[0])
                    else:
                        logging.warning("获取数据为空")
                except Exception as e:
                    logging.error(f"处理数据时出错: {str(e)}")
                
                # 等待下次检查
                time.sleep(CONFIG['check_interval'])
            
            # 交易时间结束，断开连接
            api.disconnect()
            logging.info("交易时间结束，断开连接，等待下一个交易日")
            time.sleep(60)  # 检查是否进入下一个交易时段
            
    except KeyboardInterrupt:
        logging.info("用户中断，程序退出")
        if hasattr(api, 'connected') and api.connected:
            api.disconnect()
    except Exception as e:
        logging.error(f"监控过程中发生未处理错误: {str(e)}")
    finally:
        logging.info("股票监控程序结束")

# ==================================================
# 程序入口
# ==================================================
if __name__ == "__main__":
    monitor_stock()
