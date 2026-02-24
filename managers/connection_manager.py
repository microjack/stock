import time
import logging
from pytdx.hq import TdxHq_API
from models.config_model import Config
from models.state_model import State

class ConnectionManager:
    """连接管理器"""
    
    def __init__(self):
        self.api = TdxHq_API()
    
    def initialize(self, config: Config, state: State) -> bool:
        """初始化连接"""
        try:
            if self.api.connect(config.host, config.port):
                state.is_connected = True
                state.connection_retries = 0
                state.network_retries = 0
                logging.info("成功连接TDX服务器")
                return True
            else:
                logging.warning("连接TDX服务器失败")
                return False
        except Exception as e:
            logging.error(f"连接过程中发生错误: {str(e)}")
            return False
    
    def disconnect(self, state: State):
        """断开连接"""
        if state.is_connected:
            try:
                self.api.disconnect()
                state.is_connected = False
                logging.info("已断开连接")
            except Exception as e:
                logging.error(f"断开连接时出错: {str(e)}")
    
    @staticmethod
    def should_reconnect(config: Config, state: State) -> bool:
        """检查是否需要重连"""
        # 检查连接尝试次数
        if state.connection_retries >= config.max_retries:
            logging.error(f"连接失败次数超过限制({config.max_retries})")
            return False
        
        # 检查网络重试次数
        if state.network_retries >= config.max_network_retries:
            logging.error(f"网络重试次数超过限制({config.max_network_retries})")
            return False
        
        return True