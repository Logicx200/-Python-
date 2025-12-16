import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import re
import requests
import base64
import os
import json
from pathlib import Path
from datetime import datetime
import threading
import queue
import mimetypes
from io import BytesIO
from PIL import Image
import sys

class Base64ToSMMS:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Markdown Base64图片上传工具")
        self.root.geometry("900x700")
        
        # SM.MS API配置
        self.api_token = tk.StringVar()
        self.api_url = "https://sm.ms/api/v2/upload"
        
        # 状态变量
        self.is_processing = False
        self.total_images = 0
        self.processed_images = 0
        self.failed_images = 0
        
        # 创建消息队列用于线程间通信
        self.message_queue = queue.Queue()
        
        self.setup_ui()
        
        # 检查是否有保存的API Token
        self.load_config()
        
        # 启动消息队列检查
        self.check_queue()
    
    def setup_ui(self):
        """设置用户界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # API配置区域
        ttk.Label(main_frame, text="SM.MS API Token:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        api_frame = ttk.Frame(main_frame)
        api_frame.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.api_entry = ttk.Entry(api_frame, textvariable=self.api_token, width=50, show="*")
        self.api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(api_frame, text="显示", command=self.toggle_token_visibility, width=6).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(api_frame, text="保存", command=self.save_config, width=6).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(api_frame, text="获取Token", command=self.open_smms_website, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # 文件选择区域
        ttk.Label(main_frame, text="Markdown文件:").grid(row=1, column=0, sticky=tk.W, pady=(10, 5))
        
        file_frame = ttk.Frame(main_frame)
        file_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(10, 5))
        
        self.file_path = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_path, width=50)
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(file_frame, text="浏览", command=self.browse_file, width=10).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(file_frame, text="预览图片", command=self.preview_images, width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # 输出文件选项
        ttk.Label(main_frame, text="输出文件:").grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        
        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.output_option = tk.StringVar(value="same_dir")
        ttk.Radiobutton(output_frame, text="同目录(_uploaded.md)", variable=self.output_option, 
                       value="same_dir").pack(side=tk.LEFT)
        ttk.Radiobutton(output_frame, text="覆盖原文件", variable=self.output_option, 
                       value="overwrite").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Radiobutton(output_frame, text="选择新位置", variable=self.output_option, 
                       value="custom").pack(side=tk.LEFT, padx=(20, 0))
        
        self.output_path = tk.StringVar()
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_path, width=30, state="disabled")
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        ttk.Button(output_frame, text="浏览", command=self.browse_output, width=8, 
                  state="disabled").pack(side=tk.LEFT, padx=(5, 0))
        
        # 绑定输出选项变化事件
        self.output_option.trace('w', self.on_output_option_change)
        
        # 处理选项
        options_frame = ttk.LabelFrame(main_frame, text="处理选项", padding="10")
        options_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 5))
        
        options_grid = ttk.Frame(options_frame)
        options_grid.pack(fill=tk.X, expand=True)
        
        self.skip_existing = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_grid, text="跳过已存在的图片", 
                       variable=self.skip_existing).grid(row=0, column=0, sticky=tk.W)
        
        self.backup_original = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_grid, text="处理前备份原文件", 
                       variable=self.backup_original).grid(row=0, column=1, sticky=tk.W, padx=(20, 0))
        
        self.verify_base64 = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_grid, text="验证Base64格式", 
                       variable=self.verify_base64).grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        self.fix_base64 = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_grid, text="自动修复Base64", 
                       variable=self.fix_base64).grid(row=1, column=1, sticky=tk.W, padx=(20, 0), pady=(5, 0))
        
        # 图片预览区域（隐藏，需要时显示）
        self.preview_window = None
        
        # 日志区域
        ttk.Label(main_frame, text="处理日志:").grid(row=4, column=0, sticky=tk.W, pady=(10, 5))
        
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, width=90, height=18)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置文本标签颜色
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("warning", foreground="orange")
        self.log_text.tag_config("info", foreground="blue")
        
        # 进度条和按钮区域
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(bottom_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.process_button = ttk.Button(bottom_frame, text="开始处理", command=self.start_processing, width=15)
        self.process_button.pack(side=tk.RIGHT)
        
        # 状态标签
        self.status_label = ttk.Label(bottom_frame, text="就绪")
        self.status_label.pack(side=tk.RIGHT, padx=(0, 10))
        
        # 配置网格权重
        main_frame.rowconfigure(5, weight=1)
    
    def open_smms_website(self):
        """打开SM.MS网站获取API Token"""
        import webbrowser
        webbrowser.open("https://sm.ms/home/apitoken")
        self.log("请在浏览器中登录SM.MS并获取API Token", "info")
    
    def toggle_token_visibility(self):
        """切换API Token的显示/隐藏"""
        current_state = self.api_entry.cget('show')
        if current_state == '*':
            self.api_entry.config(show='')
        else:
            self.api_entry.config(show='*')
    
    def on_output_option_change(self, *args):
        """输出选项变化时的处理"""
        option = self.output_option.get()
        if option == "custom":
            self.output_entry.config(state="normal")
            # 查找浏览按钮并启用
            for child in self.output_entry.master.winfo_children():
                if isinstance(child, ttk.Button):
                    child.config(state="normal")
        else:
            self.output_entry.config(state="disabled")
            # 查找浏览按钮并禁用
            for child in self.output_entry.master.winfo_children():
                if isinstance(child, ttk.Button):
                    child.config(state="disabled")
    
    def browse_file(self):
        """浏览选择Markdown文件"""
        filename = filedialog.askopenfilename(
            title="选择Markdown文件",
            filetypes=[("Markdown文件", "*.md;*.markdown"), ("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filename:
            self.file_path.set(filename)
            self.log(f"已选择文件: {filename}", "info")
    
    def browse_output(self):
        """浏览选择输出文件位置"""
        filename = filedialog.asksaveasfilename(
            title="选择输出文件",
            defaultextension=".md",
            filetypes=[("Markdown文件", "*.md"), ("所有文件", "*.*")]
        )
        if filename:
            self.output_path.set(filename)
            self.log(f"输出文件设置为: {filename}", "info")
    
    def preview_images(self):
        """预览Markdown中的Base64图片"""
        filepath = self.file_path.get().strip()
        if not filepath or not os.path.exists(filepath):
            messagebox.showwarning("警告", "请先选择有效的Markdown文件")
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            images = self.extract_base64_images(content)
            
            if not images:
                messagebox.showinfo("信息", "文件中未找到Base64图片")
                return
            
            # 创建预览窗口
            if self.preview_window is not None:
                self.preview_window.destroy()
            
            self.preview_window = tk.Toplevel(self.root)
            self.preview_window.title(f"图片预览 - 找到 {len(images)} 张图片")
            self.preview_window.geometry("600x500")
            
            # 创建滚动区域
            canvas = tk.Canvas(self.preview_window)
            scrollbar = ttk.Scrollbar(self.preview_window, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            # 显示每张图片的信息
            for i, img in enumerate(images):
                img_frame = ttk.LabelFrame(scrollable_frame, text=f"图片 {i+1}: {img['alt'] or '未命名'}")
                img_frame.pack(fill=tk.X, padx=10, pady=5)
                
                ttk.Label(img_frame, text=f"类型: {img['type']}").pack(anchor=tk.W, padx=5, pady=2)
                ttk.Label(img_frame, text=f"大小: {len(img['base64'])} 字节").pack(anchor=tk.W, padx=5, pady=2)
                
                # 尝试解码显示图片
                try:
                    # 清理base64数据
                    clean_base64 = self.clean_base64_data(img['base64'])
                    img_data = base64.b64decode(clean_base64)
                    
                    # 使用PIL显示图片
                    from PIL import Image, ImageTk
                    import io
                    
                    image = Image.open(io.BytesIO(img_data))
                    image.thumbnail((200, 200))
                    photo = ImageTk.PhotoImage(image)
                    
                    label = ttk.Label(img_frame, image=photo)
                    label.image = photo  # 保持引用
                    label.pack(padx=5, pady=5)
                    
                except Exception as e:
                    ttk.Label(img_frame, text=f"无法预览: {str(e)}", foreground="red").pack(padx=5, pady=5)
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
        except Exception as e:
            self.log(f"预览图片失败: {str(e)}", "error")
    
    def log(self, message, level="info"):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 在主线程中更新GUI
        self.root.after(0, self._update_log, message, level, timestamp)
    
    def _update_log(self, message, level, timestamp):
        """更新日志文本框（在主线程中调用）"""
        # 选择标签
        if level == "error":
            tag = "ERROR"
            color_tag = "error"
        elif level == "warning":
            tag = "WARN"
            color_tag = "warning"
        elif level == "success":
            tag = "SUCCESS"
            color_tag = "success"
        else:
            tag = "INFO"
            color_tag = "info"
        
        log_message = f"[{timestamp}] [{tag}] {message}\n"
        
        # 插入日志
        self.log_text.insert(tk.END, log_message)
        
        # 应用颜色标签
        start_index = f"end - {len(log_message) + 1}c"
        end_index = "end - 1c"
        self.log_text.tag_add(color_tag, start_index, end_index)
        
        # 滚动到底部
        self.log_text.see(tk.END)
    
    def update_progress(self, value):
        """更新进度条"""
        self.root.after(0, lambda: self.progress_var.set(value))
    
    def update_status(self, message):
        """更新状态标签"""
        self.root.after(0, lambda: self.status_label.config(text=message))
    
    def check_queue(self):
        """检查消息队列并处理消息"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                if message['type'] == 'log':
                    self.log(message['message'], message.get('level', 'info'))
                elif message['type'] == 'progress':
                    self.update_progress(message['value'])
                elif message['type'] == 'status':
                    self.update_status(message['message'])
                elif message['type'] == 'done':
                    self.on_processing_done(message['stats'])
        except queue.Empty:
            pass
        finally:
            # 每100ms检查一次队列
            self.root.after(100, self.check_queue)
    
    def save_config(self):
        """保存API Token到配置文件"""
        config = {
            'api_token': self.api_token.get()
        }
        config_path = Path.home() / '.md_img_uploader_config.json'
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f)
            self.log("配置已保存", "success")
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}", "error")
    
    def load_config(self):
        """从配置文件加载API Token"""
        config_path = Path.home() / '.md_img_uploader_config.json'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.api_token.set(config.get('api_token', ''))
                self.log("配置已加载", "success")
            except Exception as e:
                self.log(f"加载配置失败: {str(e)}", "warning")
    
    def clean_base64_data(self, base64_str):
        """清理Base64数据，移除非法字符"""
        # 移除空格、换行等空白字符
        cleaned = re.sub(r'\s+', '', base64_str)
        # 移除可能的数据URI剩余部分
        cleaned = re.sub(r'^data:[^,]+,', '', cleaned)
        return cleaned
    
    def validate_base64(self, base64_str):
        """验证Base64字符串是否有效"""
        try:
            # 先清理
            cleaned = self.clean_base64_data(base64_str)
            # 尝试解码
            base64.b64decode(cleaned, validate=True)
            return True, cleaned
        except Exception as e:
            return False, str(e)
    
    def extract_base64_images(self, content):
        """从Markdown内容中提取base64图片"""
        # 匹配Markdown中的base64图片
        # 格式: ![alt](data:image/类型;base64,编码字符串)
        # 支持多种变体
        patterns = [
            r'!\[(.*?)\]\(data:image/([^;]+);base64,([^)]+)\)',  # 标准格式
            r'!\[(.*?)\]\(data:image/([^;]+);([^,]+),([^)]+)\)',  # 可能有其他参数
            r'src="data:image/([^;]+);base64,([^"]+)"',  # HTML img标签
            r'background-image:\s*url\(data:image/([^;]+);base64,([^)]+)\)'  # CSS背景
        ]
        
        images = []
        
        # 标准Markdown格式
        pattern = r'!\[(.*?)\]\(data:image/([^;]+);base64,([^)]+)\)'
        matches = re.findall(pattern, content, re.IGNORECASE)
        
        for i, (alt_text, img_type, base64_data) in enumerate(matches):
            # 清理img_type，移除可能的分号
            img_type = img_type.split(';')[0].lower()
            
            # 验证和清理base64数据
            is_valid, cleaned_data = self.validate_base64(base64_data)
            
            if not is_valid and self.fix_base64.get():
                # 尝试修复
                cleaned_data = self.clean_base64_data(base64_data)
                try:
                    base64.b64decode(cleaned_data, validate=True)
                    is_valid = True
                except:
                    is_valid = False
            
            images.append({
                'index': i,
                'alt': alt_text,
                'type': img_type,
                'base64': cleaned_data if is_valid else base64_data,
                'full_match': f'![{alt_text}](data:image/{img_type};base64,{base64_data})',
                'valid': is_valid
            })
        
        return images
    
    def upload_base64_to_smms(self, base64_data, img_type, alt_text, retry_count=3):
        """上传base64图片到SM.MS - 修复版本"""
        for attempt in range(retry_count):
            try:
                # 获取API Token
                api_token = self.api_token.get().strip()
                if not api_token:
                    return None, "API Token未设置"
                
                # 确保base64数据是干净的
                cleaned_base64 = self.clean_base64_data(base64_data)
                
                # 验证base64
                if self.verify_base64.get():
                    try:
                        base64.b64decode(cleaned_base64, validate=True)
                    except Exception as e:
                        return None, f"Base64数据无效: {str(e)}"
                
                # 方法1: 使用标准multipart/form-data上传
                # SM.MS API 需要将base64数据作为文件上传
                headers = {
                    "Authorization": api_token,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                # 准备文件数据 - 关键修复：使用正确的格式
                # SM.MS API 期望一个文件，所以我们将base64解码为二进制数据
                try:
                    # 解码base64为二进制
                    binary_data = base64.b64decode(cleaned_base64)
                    
                    # 确定文件扩展名
                    ext_map = {
                        'jpeg': 'jpg', 'jpg': 'jpg',
                        'png': 'png',
                        'gif': 'gif',
                        'webp': 'webp',
                        'bmp': 'bmp'
                    }
                    extension = ext_map.get(img_type, 'png')
                    
                    # 准备文件上传
                    files = {
                        'smfile': (f'image.{extension}', binary_data, f'image/{img_type}')
                    }
                    
                    # 添加format参数
                    data = {'format': 'json'}
                    
                    # 发送请求
                    self.log(f"尝试上传图片 (尝试 {attempt + 1}/{retry_count})...", "info")
                    response = requests.post(
                        self.api_url, 
                        headers=headers, 
                        files=files, 
                        data=data,
                        timeout=30
                    )
                    
                    # 解析响应
                    result = response.json()
                    
                    # 调试信息
                    self.log(f"响应状态: {response.status_code}", "info")
                    
                    if response.status_code == 200 and result.get("success"):
                        data = result["data"]
                        markdown_link = f'![{alt_text}]({data["url"]})'
                        data['markdown'] = markdown_link
                        return data, None
                    else:
                        error_msg = result.get('message', '未知错误')
                        error_code = result.get('code', '')
                        
                        # 检查是否是重复图片
                        if error_code == 'image_repeated':
                            if 'images' in result:
                                fake_data = {
                                    'url': result['images'],
                                    'markdown': f'![{alt_text}]({result["images"]})'
                                }
                                return fake_data, "图片已存在"
                        
                        # 如果是特定错误，尝试不同的方法
                        if "Can't get target upload source info" in error_msg and attempt < retry_count - 1:
                            self.log(f"上传失败，尝试方法 {attempt + 2}...", "warning")
                            continue
                        
                        return None, f"API错误: {error_msg}"
                        
                except Exception as e:
                    if attempt < retry_count - 1:
                        self.log(f"上传异常，重试中... ({str(e)})", "warning")
                        continue
                    return None, f"上传异常: {str(e)}"
                    
            except requests.exceptions.RequestException as e:
                if attempt < retry_count - 1:
                    self.log(f"网络错误，重试中... ({str(e)})", "warning")
                    continue
                return None, f"网络错误: {str(e)}"
            except Exception as e:
                if attempt < retry_count - 1:
                    continue
                return None, f"上传失败: {str(e)}"
        
        return None, "上传失败，已重试多次"
    
    def process_file(self):
        """处理文件的主函数"""
        try:
            # 获取输入文件路径
            input_path = self.file_path.get().strip()
            if not input_path or not os.path.exists(input_path):
                self.message_queue.put({'type': 'log', 'message': '请选择有效的Markdown文件', 'level': 'error'})
                return
            
            # 读取文件内容
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取base64图片
            images = self.extract_base64_images(content)
            self.total_images = len(images)
            
            if self.total_images == 0:
                self.message_queue.put({'type': 'log', 'message': '未找到base64图片', 'level': 'warning'})
                self.message_queue.put({'type': 'done', 'stats': {'total': 0, 'success': 0, 'failed': 0}})
                return
            
            self.message_queue.put({'type': 'log', 'message': f'找到 {self.total_images} 张base64图片', 'level': 'info'})
            
            # 检查无效图片
            invalid_images = [img for img in images if not img.get('valid', True)]
            if invalid_images:
                self.message_queue.put({'type': 'log', 'message': f'发现 {len(invalid_images)} 张无效的Base64图片', 'level': 'warning'})
            
            # 备份原文件
            if self.backup_original.get():
                backup_path = input_path + '.backup'
                import shutil
                shutil.copy2(input_path, backup_path)
                self.message_queue.put({'type': 'log', 'message': f'已备份原文件到: {backup_path}', 'level': 'success'})
            
            # 处理每张图片
            success_count = 0
            failed_count = 0
            replacements = {}
            
            for i, img in enumerate(images):
                self.message_queue.put({'type': 'status', 'message': f'正在处理图片 {i+1}/{self.total_images}'})
                progress_value = (i / self.total_images) * 100
                self.message_queue.put({'type': 'progress', 'value': progress_value})
                
                alt_text = img["alt"] or f"image_{i+1}"
                self.message_queue.put({'type': 'log', 'message': f'上传图片 {i+1}: {alt_text} ({img["type"]})', 'level': 'info'})
                
                # 检查图片是否有效
                if not img.get('valid', True):
                    self.message_queue.put({'type': 'log', 'message': '  Base64数据无效，跳过上传', 'level': 'error'})
                    failed_count += 1
                    continue
                
                # 上传图片
                result, error = self.upload_base64_to_smms(img['base64'], img['type'], alt_text)
                
                if result and 'markdown' in result:
                    # 上传成功
                    replacements[img['full_match']] = result['markdown']
                    success_count += 1
                    self.message_queue.put({'type': 'log', 'message': f'  成功: {result["url"]}', 'level': 'success'})
                else:
                    # 上传失败
                    failed_count += 1
                    # 保持原样或替换为错误信息
                    if self.fix_base64.get():
                        replacements[img['full_match']] = f'<!-- 上传失败: {error} -->\n{img["full_match"]}'
                    else:
                        replacements[img['full_match']] = img['full_match']
                    self.message_queue.put({'type': 'log', 'message': f'  失败: {error}', 'level': 'error'})
            
            # 替换内容
            for old, new in replacements.items():
                content = content.replace(old, new)
            
            # 确定输出路径
            output_option = self.output_option.get()
            if output_option == "overwrite":
                output_path = input_path
            elif output_option == "same_dir":
                input_file = Path(input_path)
                output_path = str(input_file.parent / f"{input_file.stem}_uploaded.md")
            else:  # custom
                output_path = self.output_path.get().strip()
                if not output_path:
                    output_path = str(Path(input_path).parent / f"{Path(input_path).stem}_uploaded.md")
            
            # 确保输出目录存在
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # 写入输出文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 更新进度条
            self.message_queue.put({'type': 'progress', 'value': 100})
            self.message_queue.put({'type': 'status', 'message': '完成'})
            
            # 发送完成消息
            self.message_queue.put({'type': 'log', 'message': f'处理完成！成功: {success_count}, 失败: {failed_count}', 'level': 'success'})
            self.message_queue.put({'type': 'log', 'message': f'输出文件: {output_path}', 'level': 'info'})
            self.message_queue.put({'type': 'done', 'stats': {'total': self.total_images, 'success': success_count, 'failed': failed_count}})
            
        except Exception as e:
            self.message_queue.put({'type': 'log', 'message': f'处理过程出错: {str(e)}', 'level': 'error'})
            import traceback
            traceback.print_exc()
            self.message_queue.put({'type': 'done', 'stats': {'total': 0, 'success': 0, 'failed': 0}})
    
    def start_processing(self):
        """开始处理"""
        if self.is_processing:
            return
        
        # 验证输入
        if not self.api_token.get().strip():
            messagebox.showerror("错误", "请输入SM.MS API Token\n\n点击'获取Token'按钮前往SM.MS网站获取")
            return
        
        if not self.file_path.get().strip():
            messagebox.showerror("错误", "请选择Markdown文件")
            return
        
        # 清空日志
        self.log_text.delete(1.0, tk.END)
        
        # 更新UI状态
        self.is_processing = True
        self.process_button.config(state="disabled", text="处理中...")
        self.progress_var.set(0)
        
        # 在新线程中处理文件
        thread = threading.Thread(target=self.process_file, daemon=True)
        thread.start()
    
    def on_processing_done(self, stats):
        """处理完成时的回调"""
        self.is_processing = False
        self.process_button.config(state="normal", text="开始处理")
        
        # 显示总结消息
        if stats['total'] > 0:
            messagebox.showinfo("处理完成", 
                               f"图片处理完成！\n\n"
                               f"总计图片: {stats['total']}\n"
                               f"上传成功: {stats['success']}\n"
                               f"上传失败: {stats['failed']}")
    
    def run(self):
        """运行程序"""
        self.root.mainloop()

def check_dependencies():
    """检查依赖库"""
    missing_deps = []
    
    try:
        import requests
    except ImportError:
        missing_deps.append("requests")
    
    try:
        import PIL
    except ImportError:
        missing_deps.append("Pillow")
    
    if missing_deps:
        print("缺少必要的依赖库:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\n请使用以下命令安装:")
        print(f"pip install {' '.join(missing_deps)}")
        return False
    
    return True

def main():
    """主函数"""
    # 检查依赖
    if not check_dependencies():
        print("按任意键退出...")
        input()
        return
    
    # 运行应用
    app = Base64ToSMMS()
    app.run()

if __name__ == "__main__":
    main()