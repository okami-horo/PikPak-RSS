import asyncio
import urllib.request
import feedparser
import logging
import os
import sys
import time
import httpx
import json
import urllib
from logging.handlers import RotatingFileHandler
from pikpakapi import PikPakApi  # requirement: python >= 3.10
from bs4 import BeautifulSoup
from pathvalidate import sanitize_filepath

CONFIG_FILE = "config.json"     # 配置文件（保存基本配置）
CLIENT_STATE_FILE = "pikpak.json"    # 客户端状态文件（保存 PikPakApi 登录状态及 token 等信息）

# 全局变量（由配置文件或手动填写）
USER = [""]
PASSWORD = [""]
PATH = [""]
RSS = []  # RSS链接列表
RSS_TAGS = {}  # 存储RSS链接对应的标签 {rss_url: tag}
INTERVAL_TIME_RSS = 600  # rss 检查间隔
INTERVAL_TIME_REFRESH = 21600  # token 刷新间隔
PIKPAK_CLIENTS = [""]
last_refresh_time = 0
mylist = []  # 存储所有RSS源的解析结果
processed_torrents = set()  # 用于存储已处理的种子URL，避免重复处理

# CSS_Selector
BANGUMI_TITLE_SELECTOR = 'bangumi-title'

# RSS_Key
RSS_KEY_TITLE = 'title'
RSS_KEY_LINK = 'link'
RSS_KEY_TORRENT = 'enclosures'
RSS_KEY_PUB = 'published'
RSS_KEY_BGM_TITLE = 'bangumi_title'

# Regex
CHAR_RULE = "\"M\"\\a/ry/ h**ad:>> a\\/:*?\"| li*tt|le|| la\"mb.?"

# 加载基本配置文件，并更新全局变量
def load_config():
    """加载基本配置文件，并更新全局变量"""
    global RSS, RSS_TAGS, USER, PASSWORD, PATH, INTERVAL_TIME_RSS
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            # 检查必要的配置项
            if not all(key in config for key in ["username", "password", "path", "rss"]):
                logging.error("配置文件缺少必要的字段(username, password, path, rss)")
                return False
                
            # 检查用户名和密码
            USER[0] = config.get("username")
            PASSWORD[0] = config.get("password")
            
            # 检查路径 
            PATH[0] = config.get("path")
            
            # 处理RSS链接，确保是列表格式
            rss_config = config.get("rss")
            if isinstance(rss_config, str):
                # 兼容旧版本配置（单个字符串）
                RSS = [rss_config]
                logging.info(f"已加载单个RSS源: {rss_config}")
            elif isinstance(rss_config, list):
                # 新版本配置（列表）
                RSS = rss_config
                logging.info(f"已加载 {len(rss_config)} 个RSS源")
            else:
                logging.error(f"RSS配置格式错误: {type(rss_config)}")
                return False
                
            # 读取RSS标签，如果存在的话
            if "rss_tags" in config:
                RSS_TAGS = config.get("rss_tags", {})
                logging.info(f"已加载 {len(RSS_TAGS)} 个RSS标签")
            else:
                # 向后兼容：为没有标签的RSS链接创建空标签
                RSS_TAGS = {}
                
            # 检查间隔设置
            if "interval" in config:
                interval_minutes = config.get("interval", 10)
                INTERVAL_TIME_RSS = interval_minutes * 60  # 转换为秒
                
            logging.info("配置文件加载成功！")
            return True
        except json.JSONDecodeError as e:
            logging.error(f"配置文件JSON格式错误: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"加载配置文件失败: {str(e)}")
            return False
    else:
        logging.error("配置文件不存在，请创建config.json文件")
        return False


# 如果存在保存的客户端状态，则优先从 CLIENT_STATE_FILE 中加载token
# 否则根据用户名和密码新建客户端对象
def init_clients():
    global last_refresh_time
    client = None
    if os.path.exists(CLIENT_STATE_FILE):
        try:
            with open(CLIENT_STATE_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            last_refresh_time = config.get("last_refresh_time", 0)
            client_token = config.get("client_token", {})
            if client_token and client_token.get("username") == USER[0]:
                client = PikPakApi.from_dict(client_token)
                logging.info("成功从客户端状态文件加载登录状态！")
            else:
                client = PikPakApi(username=USER[0], password=PASSWORD[0])
        except Exception as e:
            logging.warning(f"加载客户端状态失败: {str(e)}，将重新创建客户端。")
            client = PikPakApi(username=USER[0], password=PASSWORD[0])
    else:
        client = PikPakApi(username=USER[0], password=PASSWORD[0])
    PIKPAK_CLIENTS[0] = client


# 保存基本配置到 CONFIG_FILE
def update_config():
    """保存基本配置到 CONFIG_FILE"""
    interval_minutes = INTERVAL_TIME_RSS // 60
    config = {
        "username": USER[0],
        "password": PASSWORD[0],
        "path": PATH[0],
        "rss": RSS,
        "rss_tags": RSS_TAGS,  # 保存RSS标签
        "interval": interval_minutes
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logging.info("配置文件更新成功！")
    except Exception as e:
        logging.error(f"配置文件更新失败: {str(e)}")

# 读取bangumi番剧名称
async def read_bangumi_title(mikan_episode_url):
    """从蜜柑计划网页中提取番剧标题
    
    Args:
        mikan_episode_url: 蜜柑计划的剧集URL
        
    Returns:
        str: 提取到的番剧标题或None（如果提取失败）
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # 设置超时和重试
        for retry in range(3):  # 尝试3次
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        mikan_episode_url, 
                        headers=headers, 
                        timeout=30.0,
                        follow_redirects=True  # 自动处理重定向
                    )
                    response.raise_for_status()  # 确保请求成功
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 尝试多种选择器查找标题
                    title_element = soup.select_one(f".{BANGUMI_TITLE_SELECTOR}")
                    
                    # 如果第一种选择器失败，尝试备用选择器
                    if not title_element:
                        title_element = soup.select_one("p.bangumi-title")
                    
                    # 如果仍然失败，尝试其他可能的选择器
                    if not title_element:
                        title_element = soup.select_one("h3.bangumi-title")

                    # 如果找到标题，返回标题文本
                    if title_element and title_element.text:
                        title = title_element.text.strip()
                        logging.info(f"成功获取番剧标题: {title}")
                        return title
                        
                    # 如果没有找到标题，尝试从URL或页面标题提取
                    page_title = soup.title.text if soup.title else None
                    if page_title and "错误" not in page_title and len(page_title) < 100:
                        logging.warning(f"使用页面标题作为番剧标题: {page_title}")
                        return page_title.strip()
                        
                    # 所有方法都失败，记录HTML以便调试
                    logging.debug(f"无法从页面提取标题，页面内容: {response.text[:500]}...")
                    
                    # 如果是最后一次尝试，返回"未知番剧"
                    if retry == 2:
                        logging.error(f"无法从URL {mikan_episode_url} 提取番剧标题")
                        return "未知番剧"
                    else:
                        # 等待一段时间后重试
                        await asyncio.sleep(2 * (retry + 1))  # 指数退避
                        
            except httpx.TimeoutException:
                if retry == 2:
                    logging.error(f"获取番剧标题超时: {mikan_episode_url}")
                    return "未知番剧"
                await asyncio.sleep(2 * (retry + 1))
                
            except httpx.HTTPStatusError as e:
                if retry == 2:
                    logging.error(f"HTTP错误 {e.response.status_code}: {str(e)}")
                    return "未知番剧"
                await asyncio.sleep(2 * (retry + 1))
                
    except Exception as e:
        logging.error(f"获取番剧标题失败: {str(e)}")
        return "未知番剧"

# 保存token到 CLIENT_STATE_FILE
def save_client():
    """保存PikPak客户端状态到文件
    
    将当前的token和刷新时间保存到CLIENT_STATE_FILE文件
    """
    # 检查客户端是否已初始化且是有效的PikPakApi对象
    if isinstance(PIKPAK_CLIENTS[0], str) or not hasattr(PIKPAK_CLIENTS[0], 'to_dict'):
        logging.warning("PikPak客户端未初始化或不是有效的对象，跳过保存客户端状态")
        return
        
    try:
        config = {
            "last_refresh_time": last_refresh_time,
            "client_token": PIKPAK_CLIENTS[0].to_dict(),
        }
        
        with open(CLIENT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logging.info("客户端状态保存成功！")
    except Exception as e:
        logging.error(f"客户端状态保存失败: {str(e)}")


# 1. 先尝试调用 file_list() 检查 token 是否有效；
# 2. 若调用失败，则重新使用用户名密码登录；
async def login(account_index):
    """尝试登录PikPak账号
    
    先检查当前token是否有效，如果无效则重新登录
    
    Args:
        account_index: 账号索引
        
    Returns:
        bool: 登录是否成功
    """
    client = PIKPAK_CLIENTS[account_index]
    max_retries = 3
    
    for retry in range(max_retries):
        try:
            # 尝试用 token 调用 file_list() 检查 token 是否有效
            await client.file_list(parent_id=PATH[account_index])
            logging.info(f"账号 {USER[account_index]} Token 有效")
            await auto_refresh_token()
            return True
        except Exception as e:
            logging.warning(f"使用 token 读取文件列表失败: {str(e)}，将尝试重新登录 (尝试 {retry+1}/{max_retries})")
            try:
                await client.login()
                logging.info(f"账号 {USER[account_index]} 登录成功！")
                await auto_refresh_token()
                return True
            except Exception as login_error:
                err_msg = str(login_error)
                if "password" in err_msg.lower() or "username" in err_msg.lower():
                    logging.error(f"账号 {USER[account_index]} 登录失败: 用户名或密码错误")
                    if retry == max_retries - 1:
                        return False
                elif "captcha" in err_msg.lower():
                    logging.error(f"账号 {USER[account_index]} 登录失败: 需要验证码，请稍后再试")
                    # 等待更长时间再重试
                    await asyncio.sleep(30 * (retry + 1))
                else:
                    logging.error(f"账号 {USER[account_index]} 登录失败: {err_msg}")
                    await asyncio.sleep(5 * (retry + 1))
                    
    logging.error(f"账号 {USER[account_index]} 登录失败，已达到最大重试次数")
    return False


# 定时刷新 token
async def auto_refresh_token():
    """刷新PikPak的访问令牌
    
    定时检查并刷新token，保持登录状态有效
    """
    global last_refresh_time
    current_time = time.time()
    
    # 检查是否需要刷新token
    if current_time - last_refresh_time >= INTERVAL_TIME_REFRESH:
        max_retries = 3
        for retry in range(max_retries):
            try:
                client = PIKPAK_CLIENTS[0]
                await client.refresh_access_token()
                logging.info("Token刷新成功！")
                last_refresh_time = current_time
                save_client()
                return
            except Exception as e:
                if "invalid_grant" in str(e).lower():
                    logging.error(f"Token刷新失败: refresh_token已过期，需要重新登录")
                    # 重置时间戳，强制下次循环进行完整登录
                    last_refresh_time = 0
                    return
                elif retry == max_retries - 1:
                    logging.error(f"Token刷新失败: {str(e)}，已达到最大重试次数")
                    # 重置时间戳，强制下次循环进行完整登录
                    last_refresh_time = 0
                else:
                    logging.warning(f"Token刷新失败: {str(e)}，将在 {2*(retry+1)} 秒后重试 ({retry+1}/{max_retries})")
                    await asyncio.sleep(2 * (retry + 1))  # 指数退避


# 解析 RSS 并返回种子列表
async def get_rss():
    """解析多个RSS源并返回合并去重后的种子列表
    
    返回的列表中每个元素包含标题、链接、种子URL、发布日期和番剧名称
    
    Returns:
        list: 包含RSS条目信息的字典列表
    """
    global processed_torrents
    all_entries = []
    
    # 遍历所有RSS源
    for rss_url in RSS:
        max_retries = 3
        for retry in range(max_retries):
            try:
                logging.info(f"正在获取RSS源: {rss_url}")
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    # 使用httpx进行请求，以支持更好的超时和错误处理
                    response = await client.get(rss_url)
                    response.raise_for_status()
                    
                    # 使用响应文本进行解析
                    rss_content = response.text
                    rss = feedparser.parse(rss_content)
                    
                    # 验证解析结果
                    if not rss.get('entries'):
                        if retry == max_retries - 1:
                            logging.error(f"RSS源 {rss_url} 解析失败或不包含条目")
                            break
                        else:
                            logging.warning(f"RSS源 {rss_url} 解析失败，将在 {2*(retry+1)} 秒后重试 ({retry+1}/{max_retries})")
                            await asyncio.sleep(2 * (retry + 1))
                            continue
                    
                    # 提取所有条目
                    current_entries = []
                    for entry in rss['entries']:
                        # 验证必要的字段是否存在
                        if RSS_KEY_TITLE not in entry or RSS_KEY_LINK not in entry or RSS_KEY_PUB not in entry:
                            logging.warning(f"RSS条目缺少必要字段: {entry.get(RSS_KEY_TITLE, '未知标题')}")
                            continue
                        
                        # 验证种子链接是否存在
                        if RSS_KEY_TORRENT not in entry or not entry[RSS_KEY_TORRENT]:
                            logging.warning(f"RSS条目缺少种子链接: {entry.get(RSS_KEY_TITLE, '未知标题')}")
                            continue
                            
                        # 提取种子URL
                        torrent_url = entry[RSS_KEY_TORRENT][0]['url'] if entry[RSS_KEY_TORRENT] else None
                        if not torrent_url:
                            continue
                            
                        # 检查是否已处理过该种子（全局去重）
                        if torrent_url in processed_torrents:
                            logging.debug(f"跳过已处理的种子: {entry.get(RSS_KEY_TITLE, '未知标题')}")
                            continue
                            
                        # 添加到当前RSS源的条目列表
                        current_entries.append(entry)
                    
                    # 并行获取番剧标题
                    if current_entries:
                        # 创建获取番剧标题的任务
                        tasks = [read_bangumi_title(entry[RSS_KEY_LINK]) for entry in current_entries]
                        bangumi_titles = await asyncio.gather(*tasks)
                        
                        # 构建结果列表
                        for i, entry in enumerate(current_entries):
                            # 将发布日期格式化为YYYY-MM-DD
                            pub_date = entry[RSS_KEY_PUB].split("T")[0] if 'T' in entry[RSS_KEY_PUB] else entry[RSS_KEY_PUB]
                            
                            # 提取种子URL
                            torrent_url = entry[RSS_KEY_TORRENT][0]['url']
                            
                            # 确保番剧标题有效
                            bgm_title = bangumi_titles[i] if i < len(bangumi_titles) else "未知番剧"
                            bgm_title = sanitize_filepath(bgm_title) if bgm_title else "未知番剧"
                            
                            # 添加到结果列表
                            all_entries.append({
                                RSS_KEY_TITLE: entry[RSS_KEY_TITLE],
                                RSS_KEY_LINK: entry[RSS_KEY_LINK],
                                RSS_KEY_TORRENT: torrent_url,
                                RSS_KEY_PUB: pub_date,
                                RSS_KEY_BGM_TITLE: bgm_title
                            })
                    
                    logging.info(f"从RSS源 {rss_url} 获取了 {len(current_entries)} 个条目")
                    # 成功获取RSS源，跳出重试循环
                    break
                    
            except httpx.TimeoutException:
                if retry == max_retries - 1:
                    logging.error(f"获取RSS源超时: {rss_url}")
                else:
                    logging.warning(f"获取RSS源超时，将在 {2*(retry+1)} 秒后重试 ({retry+1}/{max_retries})")
                    await asyncio.sleep(2 * (retry + 1))
                
            except httpx.HTTPStatusError as e:
                if retry == max_retries - 1:
                    logging.error(f"HTTP错误 {e.response.status_code}: {str(e)}")
                else:
                    logging.warning(f"HTTP错误 {e.response.status_code}，将在 {2*(retry+1)} 秒后重试 ({retry+1}/{max_retries})")
                    await asyncio.sleep(2 * (retry + 1))
                
            except Exception as e:
                if retry == max_retries - 1:
                    logging.error(f"获取RSS源时发生未知错误: {str(e)}")
                else:
                    logging.warning(f"获取RSS源时发生错误: {str(e)}，将在 {2*(retry+1)} 秒后重试 ({retry+1}/{max_retries})")
                    await asyncio.sleep(2 * (retry + 1))
    
    # 处理获取到的所有条目
    # 使用字典进行去重，以种子URL为键
    unique_entries = {}
    for entry in all_entries:
        torrent_url = entry[RSS_KEY_TORRENT]
        # 如果是新条目或者更新的版本，则保留
        if torrent_url not in unique_entries:
            unique_entries[torrent_url] = entry
            
    result = list(unique_entries.values())
    logging.info(f"从所有RSS源获取了 {len(all_entries)} 个条目，去重后剩余 {len(result)} 个")
    return result
    

# 根据番剧名称创建文件夹
async def get_folder_id(account_index, torrent):
    """根据番剧名称创建或获取PikPak中的文件夹ID
    
    Args:
        account_index: PikPak账号的索引
        torrent: 种子文件URL
        
    Returns:
        str: 文件夹ID，失败则返回None
    """
    try:
        client = PIKPAK_CLIENTS[account_index]
        folder_path = PATH[account_index]
        
        # 获取番剧标题
        title = await get_title(torrent)
        if not title:
            logging.error(f"无法获取种子 {torrent} 对应的番剧标题")
            return None
            
        # 有效性检查
        if not title or len(title.strip()) == 0:
            logging.error(f"番剧标题为空，无法创建文件夹")
            return None
            
        # 获取文件夹列表
        max_retries = 3
        folder_id = None
        
        for retry in range(max_retries):
            try:
                folder_list = await client.file_list(parent_id=folder_path)
                
                # 查找是否已存在对应名称的文件夹
                for file in folder_list.get('files', []):
                    if file['name'] == title and file['kind'] == 'drive#folder':
                        logging.info(f"找到已存在的番剧文件夹: {title} (ID: {file['id']})")
                        return file['id']
                
                # 未找到则创建新文件夹
                try:
                    folder_info = await client.create_folder(name=title, parent_id=folder_path)
                    if folder_info and 'file' in folder_info and 'id' in folder_info['file']:
                        folder_id = folder_info['file']['id']
                        logging.info(f"成功创建番剧文件夹: {title} (ID: {folder_id})")
                        return folder_id
                    else:
                        logging.error(f"创建文件夹响应格式不正确: {folder_info}")
                        if retry == max_retries - 1:
                            return None
                except Exception as e:
                    logging.error(f"创建文件夹 {title} 失败: {str(e)}")
                    if retry == max_retries - 1:
                        return None
                    await asyncio.sleep(2 * (retry + 1))
                    
            except Exception as e:
                if "not_found" in str(e).lower():
                    logging.error(f"PikPak路径 {folder_path} 不存在")
                    return None
                logging.error(f"获取文件夹列表失败: {str(e)}")
                if retry == max_retries - 1:
                    return None
                await asyncio.sleep(2 * (retry + 1))
        
        return folder_id
        
    except Exception as e:
        logging.error(f"获取或创建文件夹时发生未预期错误: {str(e)}")
        return None
    

# 通过解析 RSS 查找 torrent 对应的番剧名称
async def get_title(torrent):
    for entry in mylist:
        if entry[RSS_KEY_TORRENT] == torrent:
            logging.info(f"种子标题: {entry[RSS_KEY_TITLE]}")
            logging.info(f"番剧标题: {entry[RSS_KEY_BGM_TITLE]}")
            return entry[RSS_KEY_BGM_TITLE]
    return None


# 提交离线磁力任务至 PikPak
async def magnet_upload(account_index, file_url, folder_id):
    client = PIKPAK_CLIENTS[account_index]
    try:
        result = await client.offline_download(file_url=file_url, parent_id=folder_id)
    except Exception as e:
        logging.error(
            f"账号 {USER[account_index]} 添加离线磁力任务失败: {e}")
        return None, None
    logging.info(f"账号 {USER[account_index]} 添加离线磁力任务: {file_url}")
    return result['task']['id'], result['task']['name']


# 下载 torrent 文件并保存到本地
async def download_torrent(folder, name, torrent):
    """下载种子文件到本地
    
    Args:
        folder: 保存的文件夹路径
        name: 种子文件名
        torrent: 种子文件的URL
        
    Returns:
        str: 下载的文件路径，失败则返回None
    """
    max_retries = 3
    for retry in range(max_retries):
        try:
            # 创建文件夹（如果不存在）
            try:
                os.makedirs(folder, exist_ok=True)
            except PermissionError as e:
                logging.error(f"创建文件夹 {folder} 失败，权限不足: {str(e)}")
                return None
            except OSError as e:
                logging.error(f"创建文件夹 {folder} 失败: {str(e)}")
                return None
                
            # 下载种子文件
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    torrent, 
                    timeout=30.0,
                    follow_redirects=True
                )
                response.raise_for_status()
                
                # 验证文件是否为空
                if len(response.content) < 50:  # 一个有效的种子文件不应该小于50字节
                    logging.warning(f"下载的种子文件 {name} 疑似无效（大小：{len(response.content)}字节）")
                
                # 写入文件
                file_path = os.path.join(folder, name)
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                
                logging.info(f"种子文件下载成功: {name}")
                return file_path
                
        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP错误 {e.response.status_code} - 下载种子 {name} 失败: {str(e)}")
            if retry < max_retries - 1:
                await asyncio.sleep(2 * (retry + 1))
            else:
                return None
                
        except httpx.RequestError as e:
            logging.error(f"下载种子文件 {name} 请求失败: {str(e)}")
            if retry < max_retries - 1:
                await asyncio.sleep(2 * (retry + 1))
            else:
                return None
                
        except IOError as e:
            logging.error(f"写入种子文件 {name} 到磁盘失败: {str(e)}")
            if retry < max_retries - 1:
                await asyncio.sleep(1)
            else:
                return None
                
        except Exception as e:
            logging.error(f"下载种子文件 {name} 时发生未知错误: {str(e)}")
            if retry < max_retries - 1:
                await asyncio.sleep(2)
            else:
                return None
                
# 检查本地是否存在种子文件；若不存在则下载并提交离线任务
async def check_torrent(account_index, folder, name, torrent, check_mode: str):
    """检查本地是否存在种子文件；若不存在则下载并提交离线任务
    
    Args:
        account_index: PikPak账号的索引
        folder: 本地保存的文件夹路径
        name: 种子文件名
        torrent: 种子文件URL
        check_mode: 检查模式 "local"仅检查本地, "network"检查并下载提交
        
    Returns:
        bool: True表示需要登录或有新文件，False表示没有新文件需要处理
    """
    try:
        # 检查本地文件是否存在
        if not os.path.exists(f'{folder}/{name}'):
            if check_mode == "local":
                # 本地模式下，如果文件不存在，表示需要进行下载和提交
                return True
            else:
                # 网络模式下，先下载种子文件
                file_path = await download_torrent(folder, name, torrent)
                if not file_path:
                    logging.error(f"种子 {name} 下载失败，跳过后续处理")
                    return False
                
                try:
                    # 获取对应的文件夹ID
                    folder_id = await get_folder_id(account_index, torrent)
                    if not folder_id:
                        logging.error(f"无法获取或创建文件夹，跳过种子 {name}")
                        return False
                    
                    # 检查PikPak中是否已存在该种子文件的离线下载任务
                    info_hash = name.rsplit('.', 1)[0]
                    magnet_link = f"magnet:?xt=urn:btih:{info_hash}"
                    client = PIKPAK_CLIENTS[account_index]
                    
                    try:
                        sub_folder_list = await client.file_list(parent_id=folder_id)
                        for sub_file in sub_folder_list.get('files', []):
                            # 如果文件的URL参数与磁力链接匹配，说明已经存在
                            if sub_file.get('params', {}).get('url') == magnet_link:
                                logging.info(f"种子 {name} 已经在PikPak中存在，跳过")
                                return False
                    except Exception as e:
                        logging.error(f"获取文件夹 {folder_id} 内容失败: {str(e)}")
                        # 继续尝试提交离线下载任务
                    
                    # 提交离线下载任务
                    task_id, task_name = await magnet_upload(account_index, torrent, folder_id)
                    if task_id:
                        logging.info(f"成功添加离线下载任务: {task_name}")
                        return True
                    else:
                        logging.warning(f"添加离线下载任务失败: {torrent}")
                        return False
                        
                except Exception as e:
                    logging.error(f"处理种子 {name} 时发生错误: {str(e)}")
                    return False
        else:
            logging.debug(f"种子文件 {name} 已存在，跳过")
            return False
            
    except Exception as e:
        logging.error(f"检查种子 {name} 时发生未预期错误: {str(e)}")
        # 返回True以保证在遇到错误时仍然会尝试登录
        return True


async def process_rss():
    """处理RSS源中的新条目
    
    这是主要的业务逻辑函数，处理下载和提交离线任务
    
    Returns:
        bool: 处理是否成功
    """
    global mylist, processed_torrents
    try:
        # 刷新 token
        await auto_refresh_token()
        
        # 获取 RSS 种子列表
        mylist = await get_rss()
        if not mylist:
            logging.warning("获取到的RSS列表为空，请检查RSS链接是否有效")
            return False
            
        # 先检查本地文件是否存在，减少重复请求次数
        needLogin = False
        for entry in mylist:
            try:
                torrent = entry[RSS_KEY_TORRENT]
                name = torrent.split('/')[-1]
                folder = f'torrent/{entry[RSS_KEY_BGM_TITLE]}'
                
                # 检查本地是否存在
                if os.path.exists(f'{folder}/{name}'):
                    # 已存在的种子加入到处理集合中
                    processed_torrents.add(torrent)
                    continue
                    
                need_login_for_entry = await check_torrent(0, folder, name, torrent, "local")
                needLogin = needLogin or need_login_for_entry
            except Exception as e:
                logging.error(f"处理条目 {entry.get(RSS_KEY_TITLE, '未知标题')} 时出错: {str(e)}")
                continue

        # 如果需要下载文件，则登录（若有token，实际上是复用之前的连接状态）
        if needLogin:
            # 尝试登录所有账号
            login_tasks = [login(i) for i in range(len(USER))]
            login_results = await asyncio.gather(*login_tasks, return_exceptions=True)
            
            # 检查登录结果
            all_failed = True
            for i, result in enumerate(login_results):
                if isinstance(result, Exception):
                    logging.error(f"账号 {USER[i]} 登录失败: {str(result)}")
                elif result is True:
                    all_failed = False
                
            if all_failed:
                logging.error("所有账号登录失败，将在下次循环重试")
                return False
                
            # 遍历所有账号和 RSS 列表，串行处理避免文件夹创建冲突
            for i in range(len(USER)):
                for entry in mylist:
                    try:
                        torrent = entry[RSS_KEY_TORRENT]
                        name = torrent.split('/')[-1]
                        folder = f'torrent/{entry[RSS_KEY_BGM_TITLE]}'
                        
                        # 再次检查是否已处理（可能在处理其他账号时已经处理过）
                        if torrent in processed_torrents:
                            continue
                            
                        result = await check_torrent(i, folder, name, torrent, "network")
                        if result:
                            # 成功处理的种子加入到已处理集合
                            processed_torrents.add(torrent)
                    except Exception as e:
                        logging.error(f"处理条目 {entry.get(RSS_KEY_TITLE, '未知标题')} 时出错: {str(e)}")
                        continue
            return True
        else:
            logging.info("RSS源没有新的更新")
            return True
            
    except Exception as e:
        logging.error(f"处理RSS源时发生未预期错误: {str(e)}")
        # 保存当前状态，以免丢失
        save_client()
        return False

def setup_logging(
    log_file="rss-pikpak.log",
    log_level=logging.INFO,
    max_bytes=10*1024*1024,  # 10MB
    backup_count=5,
    handlers=None
):
    """配置日志系统
    
    Args:
        log_file: 日志文件路径
        log_level: 日志级别
        max_bytes: 单个日志文件最大大小
        backup_count: 保留的日志文件数量
        handlers: 附加的日志处理器列表
    
    Returns:
        logger: 配置好的日志记录器对象
        
    Raises:
        IOError: 日志文件路径无法访问时
        ValueError: 参数不合法时
    """
    try:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # 验证参数有效性
        if max_bytes <= 0:
            raise ValueError("max_bytes 必须大于 0")
        if backup_count < 0:
            raise ValueError("backup_count 必须大于或等于 0")
            
        # 创建logger对象
        logger = logging.getLogger()
        logger.setLevel(log_level)
        
        # 清除现有处理器，避免重复
        if logger.handlers:
            for handler in logger.handlers:
                logger.removeHandler(handler)

        # 日志格式
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 文件处理器(启用日志轮转)
        try:
            file_handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (IOError, PermissionError) as e:
            print(f"无法创建或访问日志文件 {log_file}: {str(e)}")
            # 继续程序执行，但只使用控制台输出

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 添加额外的处理器（如果有）
        if handlers:
            for handler in handlers:
                logger.addHandler(handler)

        logging.info("日志系统初始化成功")
        return logger

    except Exception as e:
        print(f"日志系统初始化失败: {str(e)}")
        # 创建一个基本的 console-only logger 作为备用
        fallback_logger = logging.getLogger()
        fallback_logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        fallback_logger.addHandler(console_handler)
        return fallback_logger


# 初始化系统
def init_system():
    """初始化系统组件"""
    setup_logging()
    if load_config():
        init_clients()
        update_config()  # 将当前基本配置写入文件（用户将配置写在main.py内的情况）
        return True
    return False