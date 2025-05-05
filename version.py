#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
版本信息管理模块
"""

# 应用版本信息
VERSION = "1.0.1"
VERSION_NAME = f"v{VERSION}"

# 构建信息
BUILD_DATE = "2025-05-05"

# 版本描述
VERSION_DESC = "Bangumi-PikPak RSS工具"

def get_version_info():
    """获取完整的版本信息字符串"""
    return f"{VERSION_NAME} ({BUILD_DATE})"

if __name__ == "__main__":
    # 打印版本信息（用于调试）
    print(get_version_info())