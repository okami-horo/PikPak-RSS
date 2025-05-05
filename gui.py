import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog
import threading
import queue
import json
import os
import sys
import time
import asyncio
import logging
from datetime import datetime
from io import StringIO

# 导入核心功能模块
import core

# 创建自定义日志处理器，将日志发送到GUI界面
class GUILogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        
    def emit(self, record):
        log_entry = self.format(record)
        self.log_queue.put(log_entry)

class BangumiPikPakGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Bangumi-PikPak 追番助手")
        self.root.geometry("900x600")
        self.root.minsize(800, 500)
        
        # 创建日志队列，用于线程间通信
        self.log_queue = queue.Queue()
        self.setup_logger()
        
        # 初始化界面
        self.create_ui()
        self.load_config()
        
        # 运行状态
        self.is_running = False
        self.task_thread = None
        
        # 设置定时检查日志队列
        self.root.after(100, self.check_log_queue)
        
    def setup_logger(self):
        """设置日志记录器，将日志同时输出到文件和GUI"""
        # 创建GUI日志处理器
        gui_handler = GUILogHandler(self.log_queue)
        gui_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        gui_handler.setFormatter(gui_formatter)
        
        # 使用核心模块的日志设置，但添加GUI处理器
        core.setup_logging(handlers=[gui_handler])
        
    def create_ui(self):
        """创建用户界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建选项卡控件
        tab_control = ttk.Notebook(main_frame)
        
        # 创建"设置"选项卡
        settings_tab = ttk.Frame(tab_control)
        tab_control.add(settings_tab, text="设置")
        
        # 创建"日志"选项卡
        log_tab = ttk.Frame(tab_control)
        tab_control.add(log_tab, text="日志")
        
        tab_control.pack(fill=tk.BOTH, expand=True)
        
        # 设置选项卡内容
        self.setup_settings_tab(settings_tab)
        self.setup_log_tab(log_tab)
        
        # 底部状态栏
        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN, padding=(5, 2))
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_label = ttk.Label(status_frame, text="就绪")
        self.status_label.pack(side=tk.LEFT)
        
        self.version_label = ttk.Label(status_frame, text="v1.0.0")
        self.version_label.pack(side=tk.RIGHT)
        
    def setup_settings_tab(self, parent):
        """设置选项卡布局和内容"""
        # 创建框架
        settings_frame = ttk.Frame(parent, padding="10")
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        # PikPak账号设置
        account_frame = ttk.LabelFrame(settings_frame, text="PikPak账号设置", padding="10")
        account_frame.pack(fill=tk.X, pady=5)
        
        # 用户名
        ttk.Label(account_frame, text="用户名:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.username_var = tk.StringVar()
        ttk.Entry(account_frame, textvariable=self.username_var, width=40).grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 密码
        ttk.Label(account_frame, text="密码:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar()
        ttk.Entry(account_frame, textvariable=self.password_var, width=40, show="*").grid(row=1, column=1, sticky=tk.W, padx=5)
        
        # 文件夹ID
        ttk.Label(account_frame, text="文件夹ID:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.folder_id_var = tk.StringVar()
        ttk.Entry(account_frame, textvariable=self.folder_id_var, width=40).grid(row=2, column=1, sticky=tk.W, padx=5)
        ttk.Label(account_frame, text="(PikPak网盘中的文件夹ID)").grid(row=2, column=2, sticky=tk.W)
        
        # RSS订阅设置
        rss_frame = ttk.LabelFrame(settings_frame, text="RSS订阅设置", padding="10")
        rss_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # RSS列表和操作按钮的框架
        rss_list_frame = ttk.Frame(rss_frame)
        rss_list_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建一个Frame来包含RSS列表和右侧的按钮
        rss_container = ttk.Frame(rss_list_frame)
        rss_container.pack(fill=tk.BOTH, expand=True)
        
        # RSS链接列表 - 使用Treeview替代Listbox以支持多列显示
        columns = ("url", "tag")
        self.rss_tree = ttk.Treeview(rss_container, columns=columns, show="headings", height=6, selectmode="extended")
        
        # 设置列标题
        self.rss_tree.heading("url", text="RSS链接")
        self.rss_tree.heading("tag", text="标签")
        
        # 设置列宽
        self.rss_tree.column("url", width=400, anchor="w")
        self.rss_tree.column("tag", width=150, anchor="w")
        
        # 添加滚动条
        rss_scrollbar = ttk.Scrollbar(rss_container, orient=tk.VERTICAL, command=self.rss_tree.yview)
        self.rss_tree.configure(yscrollcommand=rss_scrollbar.set)
        
        # 放置控件
        self.rss_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rss_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # RSS列表右侧的操作按钮
        tree_buttons_frame = ttk.Frame(rss_list_frame)
        tree_buttons_frame.pack(fill=tk.X, pady=5)
        
        # 编辑标签按钮
        ttk.Button(tree_buttons_frame, text="编辑标签", command=self.edit_tag).pack(side=tk.LEFT, padx=5)
        
        # RSS操作按钮框架
        rss_button_frame = ttk.Frame(rss_frame)
        rss_button_frame.pack(fill=tk.X, pady=5)
        
        # 新RSS链接输入框架
        input_frame = ttk.Frame(rss_button_frame)
        input_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # RSS链接输入
        ttk.Label(input_frame, text="RSS链接:").pack(side=tk.LEFT, padx=(0, 5))
        self.new_rss_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.new_rss_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 标签输入
        ttk.Label(input_frame, text="标签:").pack(side=tk.LEFT, padx=(10, 5))
        self.new_tag_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.new_tag_var, width=15).pack(side=tk.LEFT)
        
        # 按钮框架
        btn_frame = ttk.Frame(rss_button_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        # 添加按钮
        ttk.Button(btn_frame, text="添加", command=self.add_rss).pack(side=tk.LEFT, padx=5)
        
        # 删除按钮
        ttk.Button(btn_frame, text="删除", command=self.remove_rss).pack(side=tk.LEFT)
        
        # 控制按钮框架
        control_frame = ttk.Frame(settings_frame)
        control_frame.pack(fill=tk.X, pady=10)
        
        # 保存设置按钮
        ttk.Button(control_frame, text="保存设置", command=self.save_config).pack(side=tk.LEFT, padx=(0, 5))
        
        # 启动/停止按钮
        self.start_stop_btn = ttk.Button(control_frame, text="启动服务", command=self.toggle_service)
        self.start_stop_btn.pack(side=tk.LEFT)
        
        # 立即更新按钮
        ttk.Button(control_frame, text="立即更新", command=self.update_now).pack(side=tk.LEFT, padx=5)
        
        # 检查间隔设置
        interval_frame = ttk.Frame(control_frame)
        interval_frame.pack(side=tk.RIGHT)
        
        ttk.Label(interval_frame, text="检查间隔(分钟):").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="10")
        ttk.Entry(interval_frame, textvariable=self.interval_var, width=5).pack(side=tk.LEFT, padx=5)
    
    def setup_log_tab(self, parent):
        """日志选项卡布局和内容"""
        log_frame = ttk.Frame(parent, padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # 日志显示区域
        self.log_display = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=20)
        self.log_display.pack(fill=tk.BOTH, expand=True)
        self.log_display.config(state=tk.DISABLED)  # 设置为只读
        
        # 底部按钮栏
        log_buttons_frame = ttk.Frame(log_frame)
        log_buttons_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 清空日志按钮
        ttk.Button(log_buttons_frame, text="清空日志", command=self.clear_log).pack(side=tk.LEFT)
        
        # 保存日志按钮
        ttk.Button(log_buttons_frame, text="保存日志", command=self.save_log).pack(side=tk.LEFT, padx=5)
    
    def add_rss(self):
        """添加新的RSS链接到列表"""
        rss_url = self.new_rss_var.get().strip()
        rss_tag = self.new_tag_var.get().strip()
        
        if not rss_url:
            messagebox.showwarning("提示", "请输入RSS链接")
            return
            
        # 验证RSS链接格式
        if not (rss_url.startswith("http://") or rss_url.startswith("https://")):
            messagebox.showwarning("提示", "RSS链接格式不正确，必须以http://或https://开头")
            return
            
        # 避免重复添加
        current_items = self.rss_tree.get_children()
        for item in current_items:
            item_url = self.rss_tree.item(item, "values")[0]
            if rss_url == item_url:
                messagebox.showinfo("提示", "该RSS链接已存在")
                return
            
        # 添加到列表
        self.rss_tree.insert("", tk.END, values=(rss_url, rss_tag))
        self.new_rss_var.set("")  # 清空输入框
        self.new_tag_var.set("")  # 清空标签
        logging.info(f"添加RSS链接: {rss_url} 标签: {rss_tag}")
        
        # 立即更新核心模块的RSS列表和标签
        self.update_core_rss_list()
        # 更新状态栏
        self.status_label.config(text=f"已添加RSS链接，当前共有 {len(self.rss_tree.get_children())} 个RSS源")
    
    def remove_rss(self):
        """从列表中移除选中的RSS链接（支持多选）"""
        selected_items = self.rss_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择要删除的RSS链接")
            return
        
        # 确认是否删除
        count = len(selected_items)
        if count > 1:
            confirm = messagebox.askyesno("确认删除", f"确定要删除选中的 {count} 个RSS链接吗？")
        else:
            confirm = messagebox.askyesno("确认删除", "确定要删除选中的RSS链接吗？")
            
        if not confirm:
            return
            
        # 记录删除的URL，用于日志
        deleted_urls = []
        for item in selected_items:
            rss_url = self.rss_tree.item(item, "values")[0]
            deleted_urls.append(rss_url)
            
        # 删除所有选中的项
        for item in selected_items:
            self.rss_tree.delete(item)
            
        # 立即更新核心模块的RSS列表和标签
        self.update_core_rss_list()
            
        # 记录日志
        if len(deleted_urls) > 1:
            logging.info(f"批量移除 {len(deleted_urls)} 个RSS链接")
        else:
            logging.info(f"移除RSS链接: {deleted_urls[0]}")
            
        # 更新状态栏提示
        self.status_label.config(text=f"已删除 {len(deleted_urls)} 个RSS链接")
    
    def edit_tag(self):
        """编辑选中RSS链接的标签（支持多选）"""
        selected_items = self.rss_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请先选择一个或多个RSS链接")
            return
        
        # 对于单个选择，显示当前标签
        if len(selected_items) == 1:
            current_tag = self.rss_tree.item(selected_items[0], "values")[1]
            # 弹出输入框让用户输入新标签
            new_tag = simpledialog.askstring("编辑标签", "请输入新标签:", initialvalue=current_tag)
            if new_tag is not None:
                # 更新标签
                self.rss_tree.item(selected_items[0], values=(self.rss_tree.item(selected_items[0], "values")[0], new_tag))
                logging.info(f"更新RSS链接标签: {new_tag}")
                
                # 立即更新核心模块的RSS列表和标签
                self.update_core_rss_list()
                
                # 更新状态栏
                self.status_label.config(text=f"已更新RSS链接标签")
        else:
            # 多选情况下，不显示当前标签
            new_tag = simpledialog.askstring("批量编辑标签", f"请为选中的 {len(selected_items)} 个RSS链接设置新标签:")
            if new_tag is not None:
                # 批量更新所有选中项
                for item in selected_items:
                    rss_url = self.rss_tree.item(item, "values")[0]
                    self.rss_tree.item(item, values=(rss_url, new_tag))
                
                # 立即更新核心模块的RSS列表和标签
                self.update_core_rss_list()
                
                logging.info(f"已批量更新 {len(selected_items)} 个RSS链接的标签为: {new_tag}")
                # 更新状态栏
                self.status_label.config(text=f"已更新 {len(selected_items)} 个RSS链接的标签")
    
    def load_config(self):
        """从配置文件加载设置"""
        if os.path.exists(core.CONFIG_FILE):
            try:
                with open(core.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                # 设置UI控件的值
                self.username_var.set(config.get("username", ""))
                self.password_var.set(config.get("password", ""))
                self.folder_id_var.set(config.get("path", ""))
                
                # 处理RSS链接列表
                rss_links = config.get("rss", [])
                if isinstance(rss_links, str):
                    rss_links = [rss_links]
                
                # 获取RSS标签数据
                rss_tags = config.get("rss_tags", {})
                
                # 清空现有列表
                for item in self.rss_tree.get_children():
                    self.rss_tree.delete(item)
                
                # 添加RSS链接和标签到列表
                for rss in rss_links:
                    # 获取对应的标签，如果没有则显示空字符串
                    tag = rss_tags.get(rss, "")
                    self.rss_tree.insert("", tk.END, values=(rss, tag))
                    
                # 更新检查间隔
                interval_minutes = config.get("interval", 10)
                self.interval_var.set(str(interval_minutes))
                
                logging.info("配置已成功加载")
                
            except Exception as e:
                logging.error(f"加载配置失败: {str(e)}")
                messagebox.showerror("错误", f"加载配置失败: {str(e)}")
    
    def save_config(self):
        """保存设置到配置文件"""
        # 获取所有RSS链接和对应的标签
        rss_links = []
        rss_tags = {}
        
        for item in self.rss_tree.get_children():
            values = self.rss_tree.item(item, "values")
            rss_url = values[0]
            tag = values[1]
            
            rss_links.append(rss_url)  # 保存链接
            if tag:  # 只保存非空标签
                rss_tags[rss_url] = tag  # 保存标签
        
        # 获取其他设置
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        folder_id = self.folder_id_var.get().strip()
        
        # 验证必填字段
        if not username or not password or not folder_id:
            messagebox.showwarning("提示", "请填写必要的账号信息(用户名、密码和文件夹ID)")
            return
            
        if not rss_links:
            messagebox.showwarning("提示", "请至少添加一个RSS链接")
            return
            
        try:
            # 获取检查间隔
            interval = int(self.interval_var.get())
            if interval < 1:
                messagebox.showwarning("提示", "检查间隔不能小于1分钟")
                return
                
            # 更新核心模块的全局变量
            core.USER[0] = username
            core.PASSWORD[0] = password
            core.PATH[0] = folder_id
            core.RSS = rss_links
            core.RSS_TAGS = rss_tags  # 更新RSS标签
            core.INTERVAL_TIME_RSS = interval * 60  # 转换为秒
            
            # 保存配置
            core.update_config()  # 使用核心模块的方法保存配置
                
            # 如果客户端已初始化，需要重新初始化
            if hasattr(core, 'PIKPAK_CLIENTS') and core.PIKPAK_CLIENTS[0] != "":
                core.init_clients()
                
            logging.info("配置已保存")
            messagebox.showinfo("提示", "配置已保存")
            
        except ValueError:
            messagebox.showerror("错误", "检查间隔必须是数字")
        except Exception as e:
            logging.error(f"保存配置失败: {str(e)}")
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
    
    def toggle_service(self):
        """启动或停止服务"""
        if self.is_running:
            # 停止服务
            self.is_running = False
            self.start_stop_btn.config(text="启动服务")
            self.status_label.config(text="服务已停止")
            logging.info("服务已停止")
        else:
            # 启动服务
            if not os.path.exists(core.CONFIG_FILE):
                messagebox.showwarning("提示", "请先保存配置")
                return
                
            self.is_running = True
            self.start_stop_btn.config(text="停止服务")
            self.status_label.config(text="服务运行中...")
            logging.info("服务已启动")
            
            # 启动工作线程
            self.task_thread = threading.Thread(target=self.run_service, daemon=True)
            self.task_thread.start()
    
    def run_service(self):
        """在后台线程中运行服务"""
        try:
            # 初始化客户端
            core.load_config()
            core.init_clients()
            
            # 运行主循环
            while self.is_running:
                logging.info("开始检查RSS更新...")
                asyncio.run(core.process_rss())
                
                # 更新运行状态
                self.root.after(0, lambda: self.status_label.config(text=f"服务运行中... 上次更新: {datetime.now().strftime('%H:%M:%S')}"))
                
                # 等待下一次检查
                for _ in range(core.INTERVAL_TIME_RSS):
                    if not self.is_running:
                        break
                    time.sleep(1)
                    
        except Exception as e:
            logging.error(f"服务运行出错: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"服务运行出错: {str(e)}"))
            self.root.after(0, lambda: self.start_stop_btn.config(text="启动服务"))
            self.is_running = False
    
    def update_now(self):
        """立即执行一次更新"""
        if self.is_running:
            messagebox.showinfo("提示", "服务正在运行中，请等待当前任务完成")
            return
         
        # 先确保核心模块的RSS列表是最新的
        self.update_core_rss_list()
        
        # 验证是否有RSS源
        if not core.RSS:
            messagebox.showwarning("提示", "请至少添加一个RSS链接")
            return
            
        # 获取其他必要设置
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        folder_id = self.folder_id_var.get().strip()
        
        # 验证必填字段
        if not username or not password or not folder_id:
            messagebox.showwarning("提示", "请填写必要的账号信息(用户名、密码和文件夹ID)")
            return
            
        # 更新核心模块的账户信息
        core.USER[0] = username
        core.PASSWORD[0] = password
        core.PATH[0] = folder_id
        
        # 确保配置文件存在
        if not os.path.exists(core.CONFIG_FILE):
            try:
                # 先保存一次配置
                core.update_config()
            except Exception as e:
                messagebox.showwarning("提示", f"无法保存配置: {str(e)}")
                return
            
        # 启动一次性任务
        threading.Thread(target=self.run_once, daemon=True).start()
        self.status_label.config(text="正在执行更新...")
    
    def run_once(self):
        """执行一次更新任务"""
        try:
            # 初始化客户端
            core.load_config()
            core.init_clients()
            
            # 执行一次主循环
            asyncio.run(core.process_rss())
            
            # 更新状态
            self.root.after(0, lambda: self.status_label.config(text=f"更新完成 ({datetime.now().strftime('%H:%M:%S')})"))
            
        except Exception as e:
            logging.error(f"更新失败: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror("错误", f"更新失败: {str(e)}"))
            self.root.after(0, lambda: self.status_label.config(text="更新失败"))
    
    def check_log_queue(self):
        """检查日志队列并更新日志显示"""
        try:
            while True:
                log_entry = self.log_queue.get_nowait()
                self.update_log_display(log_entry)
        except queue.Empty:
            pass
        finally:
            # 每100毫秒检查一次队列
            self.root.after(100, self.check_log_queue)
    
    def update_log_display(self, log_entry):
        """更新日志显示"""
        self.log_display.config(state=tk.NORMAL)
        self.log_display.insert(tk.END, log_entry + "\n")
        self.log_display.see(tk.END)  # 自动滚动到底部
        self.log_display.config(state=tk.DISABLED)
    
    def clear_log(self):
        """清空日志显示"""
        self.log_display.config(state=tk.NORMAL)
        self.log_display.delete(1.0, tk.END)
        self.log_display.config(state=tk.DISABLED)
        logging.info("日志显示已清空")
    
    def save_log(self):
        """保存日志到文件"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("日志文件", "*.log"), ("文本文件", "*.txt"), ("所有文件", "*.*")],
            title="保存日志"
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.log_display.get(1.0, tk.END))
                messagebox.showinfo("提示", f"日志已保存到 {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存日志失败: {str(e)}")
    
    def update_core_rss_list(self):
        """从当前UI更新核心模块的RSS列表和标签
        
        此方法会收集界面上的RSS链接和标签，并更新core模块中的全局变量，
        使修改立即对更新逻辑生效，无需点击保存设置按钮
        """
        # 获取所有RSS链接和对应的标签
        rss_links = []
        rss_tags = {}
        
        for item in self.rss_tree.get_children():
            values = self.rss_tree.item(item, "values")
            rss_url = values[0]
            tag = values[1]
            
            rss_links.append(rss_url)  # 保存链接
            if tag:  # 只保存非空标签
                rss_tags[rss_url] = tag  # 保存标签
        
        # 更新核心模块的全局变量
        core.RSS = rss_links
        core.RSS_TAGS = rss_tags
        
        # 输出日志
        logging.debug(f"实时更新: RSS链接数量 {len(rss_links)}, 有标签的RSS数量 {len(rss_tags)}")
        
        # 注意：这里只更新RSS相关的变量，不更新用户名密码等配置
        # 也不写入配置文件，避免频繁IO操作

def main_gui():
    root = tk.Tk()
    app = BangumiPikPakGUI(root)
    
    # 设置窗口图标
    try:
        icon_path = os.path.join("img", "pikpak.png")
        if os.path.exists(icon_path):
            img = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, img)
    except Exception:
        pass
    
    # 正常退出时保存状态
    def on_closing():
        if messagebox.askokcancel("退出", "确定要退出吗?"):
            if app.is_running:
                app.toggle_service()  # 停止服务
            core.save_client()  # 保存客户端状态
            root.destroy()
            
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # 启动主循环
    root.mainloop()

if __name__ == "__main__":
    main_gui()