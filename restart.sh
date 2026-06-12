#!/bin/bash

# 清理
pkill -f "/Users/wangjie/pan/monitor.py" 2>/dev/null || true

# 启动
[ $(date +%H) -ge 15 ] || nohup /usr/local/bin/python /Users/wangjie/pan/monitor.py > /dev/null 2>&1 &

exit
