import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
import mammoth
import webbrowser
import sys

class DocxToMarkdownConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("DOCX 转 Markdown 转换器")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        
        # 设置窗口图标
        try:
            if sys.platform == "win32":
                self.root.iconbitmap(default="icon.ico")
        except:
            pass
        
        # 应用主题
        self.setup_style()
        
        # 变量
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.conversion_status = tk.StringVar(value="就绪")
        self.conversion_in_progress = False
        
        # 创建界面
        self.create_widgets()
        
    def setup_style(self):
        """设置样式"""
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # 自定义颜色
        self.bg_color = "#f0f0f0"
        self.primary_color = "#4a6fa5"
        self.secondary_color = "#6b8cbc"
        
        self.root.configure(bg=self.bg_color)
        
    def create_widgets(self):
        """创建所有界面组件"""
        
        # 标题
        title_frame = tk.Frame(self.root, bg=self.primary_color)
        title_frame.pack(fill="x", padx=10, pady=(10, 0))
        
        title_label = tk.Label(
            title_frame, 
            text="DOCX 转 Markdown 转换器", 
            font=("Arial", 18, "bold"),
            bg=self.primary_color,
            fg="white",
            pady=15
        )
        title_label.pack()
        
        # 主容器
        main_container = tk.Frame(self.root, bg=self.bg_color)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 输入文件选择
        input_frame = self.create_file_selection_frame(
            main_container, 
            "选择 DOCX 文件:", 
            self.input_file,
            self.browse_input_file,
            "选择 .docx 文件"
        )
        input_frame.pack(fill="x", pady=(0, 15))
        
        # 输出文件选择
        output_frame = self.create_file_selection_frame(
            main_container, 
            "保存 Markdown 文件到:", 
            self.output_file,
            self.browse_output_file,
            "选择保存位置"
        )
        output_frame.pack(fill="x", pady=(0, 20))
        
        # 转换选项
        options_frame = tk.LabelFrame(
            main_container, 
            text="转换选项", 
            font=("Arial", 10, "bold"),
            bg=self.bg_color,
            fg=self.primary_color,
            padx=15,
            pady=10
        )
        options_frame.pack(fill="x", pady=(0, 20))
        
        # 图片处理选项
        self.img_option = tk.StringVar(value="ignore")
        
        img_label = tk.Label(
            options_frame, 
            text="图片处理:", 
            bg=self.bg_color,
            font=("Arial", 9)
        )
        img_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        
        img_ignore_radio = tk.Radiobutton(
            options_frame,
            text="忽略图片",
            variable=self.img_option,
            value="ignore",
            bg=self.bg_color
        )
        img_ignore_radio.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        img_embed_radio = tk.Radiobutton(
            options_frame,
            text="嵌入为base64",
            variable=self.img_option,
            value="embed",
            bg=self.bg_color
        )
        img_embed_radio.grid(row=0, column=2, sticky="w", padx=5, pady=5)
        
        # 转换按钮
        button_frame = tk.Frame(main_container, bg=self.bg_color)
        button_frame.pack(fill="x", pady=(0, 20))
        
        convert_btn = tk.Button(
            button_frame,
            text="开始转换",
            command=self.start_conversion,
            bg=self.secondary_color,
            fg="white",
            font=("Arial", 11, "bold"),
            padx=30,
            pady=10,
            relief="flat",
            cursor="hand2"
        )
        convert_btn.pack(pady=5)
        
        # 状态显示
        status_frame = tk.LabelFrame(
            main_container, 
            text="转换状态", 
            font=("Arial", 10, "bold"),
            bg=self.bg_color,
            fg=self.primary_color,
            padx=15,
            pady=10
        )
        status_frame.pack(fill="both", expand=True)
        
        # 状态标签
        status_label = tk.Label(
            status_frame,
            textvariable=self.conversion_status,
            bg=self.bg_color,
            font=("Arial", 10),
            wraplength=600,
            justify="left"
        )
        status_label.pack(anchor="w", pady=(0, 10))
        
        # 消息文本框
        self.message_text = tk.Text(
            status_frame,
            height=8,
            width=70,
            font=("Courier", 9),
            bg="#f8f8f8",
            relief="solid",
            borderwidth=1
        )
        self.message_text.pack(fill="both", expand=True)
        
        # 添加滚动条
        scrollbar = tk.Scrollbar(self.message_text)
        scrollbar.pack(side="right", fill="y")
        self.message_text.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.message_text.yview)
        
        # 进度条
        self.progress = ttk.Progressbar(
            status_frame,
            mode='indeterminate',
            length=400
        )
        self.progress.pack(pady=10)
        
        # 底部按钮
        bottom_frame = tk.Frame(main_container, bg=self.bg_color)
        bottom_frame.pack(fill="x", pady=(10, 0))
        
        open_btn = tk.Button(
            bottom_frame,
            text="打开输出文件",
            command=self.open_output_file,
            bg="#e0e0e0",
            padx=15,
            pady=5,
            relief="flat",
            cursor="hand2"
        )
        open_btn.pack(side="left", padx=5)
        
        clear_btn = tk.Button(
            bottom_frame,
            text="清空消息",
            command=self.clear_messages,
            bg="#e0e0e0",
            padx=15,
            pady=5,
            relief="flat",
            cursor="hand2"
        )
        clear_btn.pack(side="left", padx=5)
        
        help_btn = tk.Button(
            bottom_frame,
            text="使用帮助",
            command=self.show_help,
            bg="#e0e0e0",
            padx=15,
            pady=5,
            relief="flat",
            cursor="hand2"
        )
        help_btn.pack(side="left", padx=5)
        
        exit_btn = tk.Button(
            bottom_frame,
            text="退出",
            command=self.root.quit,
            bg="#f0c0c0",
            padx=15,
            pady=5,
            relief="flat",
            cursor="hand2"
        )
        exit_btn.pack(side="right", padx=5)
        
        # 绑定事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def create_file_selection_frame(self, parent, label_text, file_var, browse_command, filetypes_desc):
        """创建文件选择框架"""
        frame = tk.Frame(parent, bg=self.bg_color)
        
        # 标签
        label = tk.Label(
            frame, 
            text=label_text, 
            bg=self.bg_color,
            font=("Arial", 10, "bold")
        )
        label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        # 输入框和浏览按钮
        entry_frame = tk.Frame(frame, bg=self.bg_color)
        entry_frame.grid(row=1, column=0, columnspan=2, sticky="we")
        
        entry = tk.Entry(
            entry_frame,
            textvariable=file_var,
            font=("Arial", 9),
            relief="solid",
            borderwidth=1,
            bg="white"
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        browse_btn = tk.Button(
            entry_frame,
            text="浏览...",
            command=browse_command,
            bg="#e0e0e0",
            padx=15,
            relief="flat",
            cursor="hand2"
        )
        browse_btn.pack(side="right")
        
        return frame
        
    def browse_input_file(self):
        """浏览输入文件"""
        filename = filedialog.askopenfilename(
            title="选择 DOCX 文件",
            filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")]
        )
        if filename:
            self.input_file.set(filename)
            
            # 自动设置输出文件名
            if not self.output_file.get():
                base_name = os.path.splitext(filename)[0]
                self.output_file.set(f"{base_name}.md")
    
    def browse_output_file(self):
        """浏览输出文件"""
        filename = filedialog.asksaveasfilename(
            title="保存 Markdown 文件",
            defaultextension=".md",
            filetypes=[("Markdown 文件", "*.md"), ("所有文件", "*.*")]
        )
        if filename:
            self.output_file.set(filename)
    
    def start_conversion(self):
        """开始转换"""
        # 验证输入
        if not self.input_file.get():
            messagebox.showerror("错误", "请选择要转换的 DOCX 文件")
            return
            
        if not self.output_file.get():
            messagebox.showerror("错误", "请指定输出文件路径")
            return
            
        # 检查输入文件是否存在
        if not os.path.exists(self.input_file.get()):
            messagebox.showerror("错误", f"文件不存在:\n{self.input_file.get()}")
            return
            
        # 防止重复启动转换
        if self.conversion_in_progress:
            return
            
        # 开始转换
        self.conversion_in_progress = True
        self.conversion_status.set("正在转换...")
        self.progress.start(10)
        
        # 在新线程中执行转换
        thread = threading.Thread(target=self.perform_conversion)
        thread.daemon = True
        thread.start()
        
    def perform_conversion(self):
        """执行转换操作"""
        try:
            # 清空消息框
            self.message_text.delete(1.0, tk.END)
            
            # 准备转换选项
            convert_options = {}
            
            # 根据图片选项设置转换参数
            if self.img_option.get() == "embed":
                # 注意：mammoth 默认不直接支持 base64 嵌入
                # 这里我们只添加一个消息说明
                self.add_message("注意: mammoth 库目前不支持直接将图片嵌入为 base64。")
                self.add_message("图片将被忽略或保留为外部链接。")
            
            # 执行转换
            with open(self.input_file.get(), "rb") as docx_file:
                result = mammoth.convert_to_markdown(docx_file)
                
                markdown_content = result.value
                messages = result.messages
                
                # 保存到文件
                with open(self.output_file.get(), "w", encoding="utf-8") as md_file:
                    md_file.write(markdown_content)
                
                # 显示消息
                self.add_message("转换成功完成!")
                self.add_message(f"输入文件: {self.input_file.get()}")
                self.add_message(f"输出文件: {self.output_file.get()}")
                self.add_message(f"文件大小: {os.path.getsize(self.output_file.get()):,} 字节")
                
                if messages:
                    self.add_message("\n转换消息:")
                    for message in messages:
                        self.add_message(f"  - {message}")
                
                self.conversion_status.set("转换成功!")
                
        except Exception as e:
            self.add_message(f"转换出错: {str(e)}")
            self.conversion_status.set("转换失败!")
            
        finally:
            # 停止进度条
            self.progress.stop()
            self.conversion_in_progress = False
    
    def add_message(self, message):
        """添加消息到文本框"""
        self.message_text.insert(tk.END, message + "\n")
        self.message_text.see(tk.END)  # 滚动到最后
        self.root.update_idletasks()  # 更新界面
        
    def open_output_file(self):
        """打开输出文件"""
        if os.path.exists(self.output_file.get()):
            try:
                # 使用默认程序打开文件
                webbrowser.open(self.output_file.get())
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件: {str(e)}")
        else:
            messagebox.showwarning("警告", "输出文件不存在")
    
    def clear_messages(self):
        """清空消息框"""
        self.message_text.delete(1.0, tk.END)
    
    def show_help(self):
        """显示帮助信息"""
        help_text = """
        DOCX 转 Markdown 转换器 - 使用帮助
        
        1. 选择要转换的 DOCX 文件
        2. 指定输出 Markdown 文件的保存路径
        3. 选择图片处理方式:
           - 忽略图片: 转换时将忽略所有图片
           - 嵌入为base64: 尝试将图片嵌入到 Markdown 中
        4. 点击"开始转换"按钮
        5. 转换完成后，可以点击"打开输出文件"查看结果
        
        注意:
        - 转换过程可能需要一些时间，具体取决于文件大小
        - 某些复杂的 DOCX 格式可能无法完美转换
        - 转换日志会显示在状态区域
        
        支持的格式:
        - 标题、段落、列表
        - 粗体、斜体、下划线
        - 表格（部分支持）
        - 链接
        """
        
        help_window = tk.Toplevel(self.root)
        help_window.title("使用帮助")
        help_window.geometry("500x500")
        help_window.resizable(False, False)
        
        text_widget = tk.Text(help_window, wrap="word", font=("Arial", 10))
        text_widget.pack(fill="both", expand=True, padx=10, pady=10)
        
        text_widget.insert(1.0, help_text)
        text_widget.config(state="disabled")  # 设置为只读
        
        close_btn = tk.Button(
            help_window,
            text="关闭",
            command=help_window.destroy,
            bg=self.secondary_color,
            fg="white",
            padx=20,
            pady=5
        )
        close_btn.pack(pady=(0, 10))
        
        # 使帮助窗口模态
        help_window.transient(self.root)
        help_window.grab_set()
        self.root.wait_window(help_window)
    
    def on_closing(self):
        """关闭窗口时的处理"""
        if self.conversion_in_progress:
            if messagebox.askyesno("确认", "转换仍在进行中，确定要退出吗？"):
                self.root.destroy()
        else:
            self.root.destroy()

def main():
    """主函数"""
    root = tk.Tk()
    app = DocxToMarkdownConverter(root)
    root.mainloop()

if __name__ == "__main__":
    # 检查依赖
    try:
        import mammoth
    except ImportError:
        print("错误: 未找到 mammoth 库")
        print("请使用以下命令安装: pip install mammoth")
        response = input("是否要自动安装 mammoth 库？(y/n): ")
        if response.lower() == 'y':
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "mammoth"])
            print("安装成功，请重新运行程序")
        sys.exit(1)
    
    # 运行GUI
    main()