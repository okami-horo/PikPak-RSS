#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bangumi-PikPak GUI启动器
"""

import os
import sys
import logging

# 确保脚本可以在任何位置运行
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

try:
    from gui import main_gui
    
    # 启动GUI
    if __name__ == "__main__":
        try:
            main_gui()
        except Exception as e:
            logging.error(f"程序启动失败: {str(e)}")
            print(f"程序启动失败: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 保持控制台窗口
            if sys.platform.startswith('win'):
                input("按Enter键退出...")
except ImportError as e:
    print(f"导入错误: {str(e)}")
    print("请确保已安装所有必要的依赖。")
    
    # 尝试安装依赖
    try:
        import pip
        print("正在尝试安装必要依赖...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "feedparser", "beautifulsoup4", "pathvalidate", "pikpakapi>=0.1.0"])
        print("依赖安装完成，请重新启动程序。")
    except Exception as install_error:
        print(f"安装依赖失败: {str(install_error)}")
    
    if sys.platform.startswith('win'):
        input("按Enter键退出...")