# build.py - 用于打包应用程序的脚本
import os
import sys
import shutil

# 确保当前目录是项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)

print("开始打包Bangumi-PikPak为可执行文件...")

# 构建打包命令
# 移除--icon参数，避免需要Pillow库
cmd = 'pyinstaller --noconfirm --clean --name "Bangumi-PikPak" --windowed --add-data "img;img" gui.py'

# 执行打包命令
os.system(cmd)

# 打包完成后，拷贝一些必要文件到dist目录
dist_dir = os.path.join(project_root, "dist", "Bangumi-PikPak")

# 如果配置文件存在，可以选择是否拷贝（如果不希望用户配置被覆盖）
# 取消注释下面的代码以复制配置文件
config_files = ["config.json", "pikpak.json"]
for config_file in config_files:
    src = os.path.join(project_root, config_file)
    dst = os.path.join(dist_dir, config_file)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f"已复制 {config_file} 到发布目录")

# 创建torrent目录（如果需要）
torrent_dir = os.path.join(dist_dir, "torrent")
if not os.path.exists(torrent_dir):
    os.makedirs(torrent_dir)
    print("已创建torrent目录")

print(f"\n打包完成！可执行文件位于: {dist_dir}")
print("你可以直接运行 Bangumi-PikPak.exe 来启动应用程序")