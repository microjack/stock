#!/bin/bash

# 清理
ps aux | grep "/Users/wangjie/pan/monitor.py" | grep -v grep | awk '{print $2}' | xargs kill -9

# 启动
nohup /usr/local/bin/python /Users/wangjie/pan/monitor.py > /dev/null 2>&1 &
