import time
import logging
import socket
from typing import Optional
from models.config_model import Config
from models.state_model import State

class NetworkManager:
    """网络管理器"""
    
    @staticmethod
    def check_connection(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> bool:
        """检查网络连接状态"""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception:
            return False
    
    @staticmethod
    def wait_for_recovery(config: Config, state: State) -> bool:
        """等待网络恢复"""
        retry_count = 0
        while retry_count < config.max_network_retries:
            if NetworkManager.check_connection():
                logging.info("网络连接已恢复")
                state.network_retries = 0
                return True
            
            retry_count += 1
            wait_time = config.network_retry_delay * (2 ** (retry_count - 1))
            logging.warning(f"网络连接失败，第{retry_count}次重试，等待{wait_time}秒...")
            time.sleep(wait_time)
        
        logging.error("网络连接失败超过最大重试次数")
        return False