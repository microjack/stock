import time
import logging
from datetime import datetime
from typing import Optional

from config import ConfigManager
from managers import NetworkManager, TimeManager, NotificationManager, DataProcessor, ConnectionManager, LogManager
from models.config_model import Config
from models.state_model import State

class StockMonitor:
    """股票监控器"""
    
    def __init__(self):
        self.config: Config = ConfigManager.get_config()
        self.state: State = State()
        self.connection_manager: ConnectionManager = ConnectionManager()
    
    def process_trading_data(self, data: dict):
        """处理交易数据"""
        # 解析数据
        current_price, _, difference_ratio, amount = DataProcessor.parse_data(data)
        
        # 获取时间信息
        time_str, seconds = TimeManager.get_time_info()
        
        # 检查成交量变化
        volume_change = DataProcessor.check_volume_change(
            self.config, self.state, amount, seconds
        )
        
        if volume_change is not None:
            self.send_notification_with_cooldown(
                "成交量提醒", 
                f"{self.config.stock_code} 成交量增加 {volume_change}万"
            )
        
        # 检查价格变化
        price_changed, direction = DataProcessor.check_price_change(
            self.config, difference_ratio
        )
        
        if price_changed:
            self.send_notification_with_cooldown(
                "价格波动警告", 
                f"{self.config.stock_code} {direction}{abs(difference_ratio)}%", 
                critical=True
            )
        
        # 记录日志
        LogManager.log_stock_data(time_str, current_price, difference_ratio, amount)
        
        # 保存价格并更新状态
        self.state.last_price = current_price
        self.state.update_successful_check()
    
    def send_notification_with_cooldown(self, title: str, message: str, critical: bool = False):
        """带冷却时间的通知发送"""
        if NotificationManager.can_send_notification(self.config, self.state):
            NotificationManager.send(title, message, critical)
            self.state.last_notification_time = datetime.now()
            logging.info(f"已发送通知: {title} - {message}")
    
    def check_connection_status(self) -> bool:
        """检查连接状态"""
        # 检查最后成功获取数据的时间
        if self.state.last_successful_check:
            time_since_last = (datetime.now() - self.state.last_successful_check).total_seconds()
            if time_since_last > self.config.network_check_interval * 3:
                logging.warning("长时间未获取到数据，可能连接已断开")
                return False
        
        return True
    
    def handle_trading_session(self) -> bool:
        """处理交易时段"""
        logging.info("进入交易时段监控")
        
        while TimeManager.is_trading_hours(self.config):
            # 检查网络连接
            if not NetworkManager.check_connection():
                logging.warning("网络连接中断")
                self.connection_manager.disconnect(self.state)
                self.send_notification_with_cooldown(
                    "股票监控", "网络连接中断，正在尝试重连", critical=True
                )
                return False
            
            # 检查连接状态
            if not self.check_connection_status():
                self.connection_manager.disconnect(self.state)
                return False
            
            try:
                # 获取股票数据
                response = self.connection_manager.api.get_security_quotes([
                    (self.config.market_code, self.config.stock_code)
                ])
                
                if response:
                    self.process_trading_data(response[0])
                else:
                    logging.warning("获取数据为空，可能连接异常")
                    self.connection_manager.disconnect(self.state)
                    return False
                
                time.sleep(self.config.check_interval)
                
            except Exception as e:
                logging.error(f"处理数据时出错: {str(e)}")
                self.connection_manager.disconnect(self.state)
                
                # 检查是否是网络相关错误
                error_msg = str(e).lower()
                network_errors = ['timeout', 'connection', 'socket', 'network', 'reset']
                if any(err in error_msg for err in network_errors):
                    logging.warning("网络相关错误，等待网络恢复")
                
                return False
        
        return True
    
    def handle_non_trading_hours(self):
        """处理非交易时段"""
        logging.info("当前非交易时间，等待60秒后重试")
        
        if self.state.is_connected:
            self.connection_manager.disconnect(self.state)
        
        time.sleep(60)
    
    def handle_connection_attempt(self) -> bool:
        """处理连接尝试"""
        if not self.connection_manager.initialize(self.config, self.state):
            self.state.connection_retries += 1
            
            if not self.connection_manager.should_reconnect(self.config, self.state):
                return False
            
            logging.warning(f"连接失败，{self.config.retry_delay}秒后重试...")
            time.sleep(self.config.retry_delay)
            return False
        
        return True
    
    def handle_network_recovery(self) -> bool:
        """处理网络恢复"""
        if not NetworkManager.wait_for_recovery(self.config, self.state):
            self.send_notification_with_cooldown(
                "股票监控", "网络连接失败，程序退出", critical=True
            )
            return False
        
        return True
    
    def monitor(self):
        """主监控循环"""
        logging.info("股票监控程序启动")
        self.send_notification_with_cooldown("股票监控", "监控程序已启动")
        
        try:
            while True:
                # 检查是否在交易时间
                if not TimeManager.is_trading_hours(self.config):
                    self.handle_non_trading_hours()
                    continue
                
                # 检查网络连接
                if not NetworkManager.check_connection():
                    logging.warning("网络连接异常")
                    if not self.handle_network_recovery():
                        break
                    continue
                
                # 如果未连接，则尝试连接
                if not self.state.is_connected:
                    if not self.handle_connection_attempt():
                        continue
                
                # 处理交易时段
                if not self.handle_trading_session():
                    continue
                
        except KeyboardInterrupt:
            logging.info("用户中断，程序退出")
        except Exception as e:
            logging.error(f"监控过程中发生未处理错误: {str(e)}")
            self.send_notification_with_cooldown(
                "股票监控", f"监控程序异常退出: {str(e)}", critical=True
            )
        finally:
            self.cleanup()
    
    def cleanup(self):
        """清理资源"""
        self.connection_manager.disconnect(self.state)
        self.send_notification_with_cooldown("股票监控", "监控程序已停止", critical=True)
        logging.info("股票监控程序结束")