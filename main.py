#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bangumi-PikPak RSS 命令行工具
用于自动从RSS源获取番剧种子并提交到PikPak离线下载
"""

import os
import sys
import time
import signal
import asyncio
import logging

# 导入核心功能模块
import core

def signal_handler(sig, frame):
    """处理退出信号"""
    logging.info("正在保存状态并退出...")
    core.save_client()  # 保存客户端状态
    core.update_config()  # 保存配置
    sys.exit(0)

async def main_loop():
    """主循环函数"""
    while True:
        try:
            # 执行一次RSS处理
            await core.process_rss()
        except Exception as e:
            logging.error(f"执行周期任务时发生错误: {str(e)}")
        finally:
            # 保存当前状态
            core.save_client()
            
        # 等待下一次检查
        logging.info(f"等待 {core.INTERVAL_TIME_RSS} 秒后执行下一次检查...")
        await asyncio.sleep(core.INTERVAL_TIME_RSS)

def main():
    """主函数"""
    # 初始化系统
    if not core.init_system():
        logging.error("系统初始化失败，请检查配置文件")
        return

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logging.info("Bangumi-PikPak RSS 命令行工具已启动")
    logging.info(f"当前配置: 用户 {core.USER[0]}, {len(core.RSS)} 个RSS源, 检查间隔 {core.INTERVAL_TIME_RSS}秒")
    
    try:
        # 运行主循环
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("接收到退出信号，保存状态并退出...")
    except Exception as e:
        logging.error(f"程序运行出错: {str(e)}")
    finally:
        core.save_client()
        core.update_config()

if __name__ == "__main__":
    main()
