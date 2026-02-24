from managers.log_manager import LogManager
from monitor import StockMonitor

def main():
    """主函数"""
    # 设置日志
    LogManager.setup_logging()
    
    # 创建并启动监控器
    monitor = StockMonitor()
    monitor.monitor()

if __name__ == "__main__":
    main()