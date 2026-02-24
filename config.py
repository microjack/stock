from models.config_model import Config

class ConfigManager:
    """配置管理器"""
    
    @staticmethod
    def get_config() -> Config:
        """获取配置参数"""
        return Config(
            host='111.229.247.189',
            port=7709,
            market_code=2,
            stock_code="920579",
            trading_ranges=[("09:30", "11:30"), ("13:00", "15:00")],
            check_interval=1,
            max_retries=3,
            retry_delay=5,
            network_check_interval=10,
            max_network_retries=5,
            network_retry_delay=30,
            volume_threshold=100,
            price_change_threshold=5.0,
            notification_cooldown=60,
        )