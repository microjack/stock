import logging

class LogManager:
    """日志管理器"""
    
    @staticmethod
    def setup_logging():
        """设置日志配置"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("stock_monitor.log"),
                logging.StreamHandler()
            ]
        )
    
    @staticmethod
    def log_stock_data(time_str: str, current_price: float, 
                      difference_ratio: float, amount: int):
        """记录股票数据"""
        logging.info(
            f"时间: {time_str} | "
            f"价格: {current_price} | "
            f"涨跌幅: {difference_ratio}% | "
            f"成交量: {amount}万"
        )