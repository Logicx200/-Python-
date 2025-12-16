"""
完整版视频标志物跟踪分析系统
包含：光流跟踪、重新标记、阻尼分析等功能
修复了重新标记模式下鼠标点击无响应的问题
"""

import cv2
import numpy as np
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
import json
import pandas as pd
import warnings
import sys
import time
from PIL import Image, ImageDraw, ImageFont
import matplotlib
from scipy.optimize import curve_fit

# 配置Matplotlib显示中文
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

warnings.filterwarnings('ignore')

def damping_model(t, A, b, y0):
    """阻尼模型函数：A * exp(-b * t) + y0"""
    return A * np.exp(-b * t) + y0

class ChineseTextDrawer:
    """中文文本绘制器"""
    
    def __init__(self):
        self.fonts = {}
        self.load_fonts()
    
    def load_fonts(self):
        """加载字体"""
        try:
            # 尝试加载常见的中文字体
            font_paths = [
                "C:/Windows/Fonts/simhei.ttf",      # 黑体
                "C:/Windows/Fonts/msyh.ttc",        # 微软雅黑
                "C:/Windows/Fonts/simsun.ttc",      # 宋体
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # Linux
                "/System/Library/Fonts/PingFang.ttc",  # macOS
            ]
            
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        # 加载不同大小的字体
                        self.fonts[10] = ImageFont.truetype(path, 10)
                        self.fonts[12] = ImageFont.truetype(path, 12)
                        self.fonts[14] = ImageFont.truetype(path, 14)
                        self.fonts[16] = ImageFont.truetype(path, 16)
                        self.fonts[18] = ImageFont.truetype(path, 18)
                        self.fonts[20] = ImageFont.truetype(path, 20)
                        self.fonts[24] = ImageFont.truetype(path, 24)
                        print(f"成功加载字体: {path}")
                        break
                    except Exception as e:
                        print(f"加载字体失败 {path}: {e}")
                        continue
            
            # 如果没有找到字体，使用默认字体
            if not self.fonts:
                print("警告: 未找到中文字体，使用默认字体")
                self.fonts[12] = ImageFont.load_default()
        
        except Exception as e:
            print(f"字体加载错误: {e}")
            self.fonts[12] = ImageFont.load_default()
    
    def put_chinese_text(self, image, text, position, font_size=16, color=(255, 255, 255)):
        """
        在图像上绘制中文文本
        
        参数:
            image: OpenCV图像 (numpy数组)
            text: 要绘制的文本
            position: (x, y) 文本位置
            font_size: 字体大小
            color: 字体颜色 (B, G, R)
        
        返回:
            带有中文文本的图像
        """
        if font_size not in self.fonts:
            font_size = 16  # 默认大小
        
        # 将OpenCV图像转换为PIL图像
        if len(image.shape) == 2:  # 灰度图
            pil_image = Image.fromarray(image)
            pil_image = pil_image.convert('RGB')
        else:  # BGR彩色图
            # OpenCV使用BGR，PIL使用RGB，需要转换
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(image_rgb)
        
        # 创建绘图对象
        draw = ImageDraw.Draw(pil_image)
        
        # 反转颜色顺序 (BGR -> RGB)
        color_rgb = (color[2], color[1], color[0])
        
        # 绘制文本
        try:
            draw.text(position, text, font=self.fonts[font_size], fill=color_rgb)
        except Exception as e:
            print(f"绘制文本失败: {e}")
            # 使用默认字体重试
            draw.text(position, text, font=ImageFont.load_default(), fill=color_rgb)
        
        # 转换回OpenCV格式
        result = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        
        return result
    
    def draw_text_box(self, image, text, position, font_size=16, text_color=(255, 255, 255), 
                     box_color=(0, 0, 0), box_alpha=0.7):
        """
        绘制带有背景框的文本
        
        参数:
            image: OpenCV图像
            text: 要绘制的文本
            position: (x, y) 文本位置
            font_size: 字体大小
            text_color: 文本颜色
            box_color: 背景框颜色
            box_alpha: 背景框透明度
        
        返回:
            带有文本和背景框的图像
        """
        # 先绘制背景框
        if self.fonts.get(font_size):
            # 创建一个临时图像来测量文本大小
            temp_img = Image.new('RGB', (100, 100), (0, 0, 0))
            temp_draw = ImageDraw.Draw(temp_img)
            
            # 获取文本边界框
            try:
                font = self.fonts[font_size]
                bbox = temp_draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                # 如果获取边界框失败，使用估计值
                text_width = len(text) * font_size
                text_height = font_size
            
            # 计算背景框位置和大小
            x, y = position
            padding = 5
            rect_x1 = x - padding
            rect_y1 = y - padding
            rect_x2 = x + text_width + padding
            rect_y2 = y + text_height + padding
            
            # 绘制半透明背景框
            overlay = image.copy()
            cv2.rectangle(overlay, (rect_x1, rect_y1), (rect_x2, rect_y2), box_color, -1)
            image = cv2.addWeighted(overlay, box_alpha, image, 1 - box_alpha, 0)
        
        # 绘制文本
        return self.put_chinese_text(image, text, position, font_size, text_color)

class OpticalFlowTracker:
    """光流法跟踪器"""
    
    def __init__(self):
        self.prev_gray = None
        self.points = {}
        self.status = {}
        self.lk_params = dict(
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )
        self.feature_params = dict(
            maxCorners=100,
            qualityLevel=0.3,
            minDistance=7,
            blockSize=7
        )
    
    def initialize(self, frame, points):
        """初始化跟踪点"""
        self.prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.points = {i: np.array([pt], dtype=np.float32).reshape(-1, 1, 2) 
                      for i, pt in enumerate(points)}
        self.status = {i: True for i in range(len(points))}
        return True
    
    def update(self, frame):
        """更新跟踪点"""
        if self.prev_gray is None:
            return False, None
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        new_points = {}
        new_status = {}
        
        for i in self.points:
            if self.status[i]:  # 只更新当前状态为true的点
                # 计算光流
                next_pts, status, err = cv2.calcOpticalFlowPyrLK(
                    self.prev_gray, gray, self.points[i], None, **self.lk_params)
                
                if status[0] == 1:  # 跟踪成功
                    new_points[i] = next_pts
                    new_status[i] = True
                else:  # 跟踪失败
                    new_points[i] = self.points[i]  # 保持原位置
                    new_status[i] = False
        
        self.points = new_points
        self.status = new_status
        self.prev_gray = gray.copy()
        
        return True, self.points
    
    def get_points(self):
        """获取当前跟踪点"""
        return {i: self.points[i][0][0] if self.status[i] else None 
                for i in self.points}
    
    def get_status(self):
        """获取跟踪状态"""
        return self.status

class EnhancedVideoMarkerTracker:
    def __init__(self):
        self.video_path = None
        self.cap = None
        self.current_frame = None
        self.frame_count = 0
        self.fps = 0
        self.width = 0
        self.height = 0
        
        # 中文文本绘制器
        self.text_drawer = ChineseTextDrawer()
        
        # 标定相关
        self.scale_factor = 1.0  # 像素/cm
        self.reference_points = []
        self.reference_distance = 0
        
        # 跟踪相关
        self.tracking_points = []
        self.tracked_positions = {}
        self.tracking_active = False
        self.optical_flow_tracker = OpticalFlowTracker()
        
        # 置信度相关
        self.confidence_threshold = 0.5
        self.tracking_confidences = {}
        self.low_confidence_frames = {}
        self.position_history = {}
        
        # 可视化
        self.fig, self.ax = None, None
        self.colors = [
            (255, 0, 0),    # 红色
            (0, 255, 0),    # 绿色
            (0, 0, 255),    # 蓝色
            (255, 255, 0),  # 黄色
            (255, 0, 255),  # 粉色
            (0, 255, 255),  # 青色
            (255, 128, 0),  # 橙色
            (128, 0, 255)   # 紫色
        ]
        
        # 平滑处理
        self.smoothing_window = 5
        
        # 重新标定相关
        self.recalibration_needed = False
        self.recalibrate_points = []
        self.current_recalibrating_index = None
        
        # 多帧显示相关
        self.nearby_frames_to_show = 5  # 显示邻近的5帧
        
        # 添加新的状态变量
        self.current_tracking_frame = 0
        self.is_recalibrating = False
        self.selected_marker_for_recalibration = None  # 用于重新标记的选定标记点
        self.recalibration_start_frame = 0  # 重新标记的起始帧

        # 阻尼系数相关
        self.damping_segments = {}  # 存储每个标记点的阻尼段
        self.damping_coefficients = {}  # 存储计算出的阻尼系数
        self.selected_damping_segment = None  # 当前选择的阻尼段
    
    def select_video_file(self):
        """选择视频文件"""
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv"),
                ("MP4文件", "*.mp4"),
                ("AVI文件", "*.avi"),
                ("所有文件", "*.*")
            ]
        )
        return file_path
    
    def load_video(self, video_path=None):
        """加载视频"""
        if video_path is None:
            video_path = self.select_video_file()
        
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("错误", "未选择视频文件或文件不存在")
            return False
        
        if self.cap is not None:
            self.cap.release()
        
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        
        if not self.cap.isOpened():
            messagebox.showerror("错误", "无法打开视频文件")
            return False
        
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        ret, frame = self.cap.read()
        if ret:
            self.current_frame = frame.copy()
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        else:
            messagebox.showerror("错误", "无法读取视频帧")
            return False
        
        print(f"已加载视频: {os.path.basename(self.video_path)}")
        print(f"视频信息: {self.width}x{self.height}, {self.frame_count} 帧, {self.fps:.1f} FPS")
        
        return True
    
    def calibrate_coordinate_system(self):
        """标定坐标系"""
        if self.current_frame is None:
            messagebox.showwarning("警告", "请先加载视频")
            return False
        
        cal_frame = self.current_frame.copy()
        points = []
        
        def mouse_callback(event, x, y, flags, param):
            nonlocal cal_frame, points
            
            if event == cv2.EVENT_LBUTTONDOWN:
                if len(points) < 2:
                    points.append((x, y))
                    cal_frame = self.current_frame.copy()
                    
                    # 绘制点
                    for i, pt in enumerate(points):
                        cv2.circle(cal_frame, pt, 8, (0, 255, 0), -1)
                        # 使用中文文本绘制器
                        cal_frame = self.text_drawer.put_chinese_text(
                            cal_frame, f"点{i+1}", (pt[0]+10, pt[1]-10),
                            font_size=12, color=(0, 255, 0)
                        )
                    
                    if len(points) == 1:
                        # 绘制提示信息
                        cal_frame = self.text_drawer.draw_text_box(
                            cal_frame, "选择第一个参考点", (10, 30),
                            font_size=14, text_color=(0, 255, 0)
                        )
                        cal_frame = self.text_drawer.draw_text_box(
                            cal_frame, "ESC取消，右键删除上一个点", (10, 60),
                            font_size=12, text_color=(255, 255, 255)
                        )
                    elif len(points) == 2:
                        # 绘制连接线
                        cv2.line(cal_frame, points[0], points[1], (0, 255, 0), 2)
                        distance_px = np.sqrt((points[1][0] - points[0][0])**2 + 
                                            (points[1][1] - points[0][1])**2)
                        
                        cal_frame = self.text_drawer.draw_text_box(
                            cal_frame, f"像素距离: {distance_px:.1f} px", (10, 90),
                            font_size=14, text_color=(0, 255, 0)
                        )
                        cal_frame = self.text_drawer.draw_text_box(
                            cal_frame, "按任意键继续...", (10, 120),
                            font_size=12, text_color=(255, 255, 255)
                        )
                    
                    cv2.imshow("Calibration", cal_frame)
            
            elif event == cv2.EVENT_RBUTTONDOWN:
                if points:
                    points.pop()
                    cal_frame = self.current_frame.copy()
                    
                    for i, pt in enumerate(points):
                        cv2.circle(cal_frame, pt, 8, (0, 255, 0), -1)
                        cal_frame = self.text_drawer.put_chinese_text(
                            cal_frame, f"点{i+1}", (pt[0]+10, pt[1]-10),
                            font_size=12, color=(0, 255, 0)
                        )
                    
                    if len(points) == 1:
                        cal_frame = self.text_drawer.draw_text_box(
                            cal_frame, "选择第二个参考点", (10, 30),
                            font_size=14, text_color=(0, 255, 0)
                        )
                    
                    cv2.imshow("Calibration", cal_frame)
        
        cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Calibration", min(800, self.width), min(600, self.height))
        cv2.setMouseCallback("Calibration", mouse_callback)
        
        # 绘制初始提示
        cal_frame = self.text_drawer.draw_text_box(
            cal_frame, "标定坐标系", (10, 30),
            font_size=16, text_color=(0, 255, 0)
        )
        cal_frame = self.text_drawer.draw_text_box(
            cal_frame, "1. 左键选择两个参考点", (10, 60),
            font_size=12, text_color=(255, 255, 255)
        )
        cal_frame = self.text_drawer.draw_text_box(
            cal_frame, "2. 右键删除上一个点", (10, 85),
            font_size=12, text_color=(255, 255, 255)
        )
        cal_frame = self.text_drawer.draw_text_box(
            cal_frame, "3. 按ESC取消，选择两个点后按任意键继续", (10, 110),
            font_size=12, text_color=(255, 255, 255)
        )
        
        cv2.imshow("Calibration", cal_frame)
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                cv2.destroyWindow("Calibration")
                return False
            elif len(points) == 2 and key != 255:
                break
        
        cv2.destroyWindow("Calibration")
        
        distance_px = np.sqrt((points[1][0] - points[0][0])**2 + 
                            (points[1][1] - points[0][1])**2)
        
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        distance_cm = simpledialog.askfloat(
            "输入实际距离",
            f"像素距离: {distance_px:.1f} 像素\n\n请输入两点之间的实际距离(cm):",
            parent=root,
            minvalue=0.1,
            maxvalue=1000.0,
            initialvalue=10.0
        )
        root.destroy()
        
        if distance_cm and distance_cm > 0:
            self.scale_factor = distance_cm / distance_px
            self.reference_points = points
            self.reference_distance = distance_cm
            
            messagebox.showinfo("标定完成", 
                               f"标定完成！\n"
                               f"像素距离: {distance_px:.1f} px\n"
                               f"实际距离: {distance_cm:.1f} cm\n"
                               f"比例尺: 1像素 = {self.scale_factor:.4f} cm\n"
                               f"1cm = {1/self.scale_factor:.1f} 像素")
            return True
        
        return False
    
    def select_markers(self):
        """手动选择要跟踪的标志物"""
        if self.current_frame is None:
            messagebox.showwarning("警告", "请先加载视频")
            return False
        
        select_frame = self.current_frame.copy()
        markers = []
        
        def mouse_callback(event, x, y, flags, param):
            nonlocal select_frame, markers
            
            if event == cv2.EVENT_LBUTTONDOWN:
                markers.append((x, y))
                select_frame = self.current_frame.copy()
                
                # 绘制所有已选择的标记
                for i, pt in enumerate(markers):
                    color_idx = i % len(self.colors)
                    color = self.colors[color_idx]
                    cv2.circle(select_frame, pt, 10, color, -1)
                    cv2.circle(select_frame, pt, 12, (255, 255, 255), 2)
                    
                    # 使用OpenCV绘制数字（英文数字不会乱码）
                    cv2.putText(select_frame, str(i+1), (pt[0]-5, pt[1]+5), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                
                # 显示操作提示（使用中文绘制器）
                select_frame = self.text_drawer.draw_text_box(
                    select_frame, "选择标志物", (20, 35),
                    font_size=14, text_color=(255, 255, 255)
                )
                select_frame = self.text_drawer.draw_text_box(
                    select_frame, f"已选择 {len(markers)} 个标记", (20, 65),
                    font_size=12, text_color=(255, 255, 255)
                )
                select_frame = self.text_drawer.draw_text_box(
                    select_frame, "左键: 添加标记", (20, 90),
                    font_size=12, text_color=(255, 255, 255)
                )
                select_frame = self.text_drawer.draw_text_box(
                    select_frame, "右键: 删除上一个 | 空格: 完成 | ESC: 取消", 
                    (20, 115), font_size=12, text_color=(255, 255, 255)
                )
                
                cv2.imshow("Select Markers", select_frame)
            
            elif event == cv2.EVENT_RBUTTONDOWN:
                if markers:
                    markers.pop()
                    select_frame = self.current_frame.copy()
                    
                    for i, pt in enumerate(markers):
                        color_idx = i % len(self.colors)
                        color = self.colors[color_idx]
                        cv2.circle(select_frame, pt, 10, color, -1)
                        cv2.circle(select_frame, pt, 12, (255, 255, 255), 2)
                        cv2.putText(select_frame, str(i+1), (pt[0]-5, pt[1]+5), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                    
                    # 显示操作提示
                    select_frame = self.text_drawer.draw_text_box(
                        select_frame, "选择标志物", (20, 35),
                        font_size=14, text_color=(255, 255, 255)
                    )
                    select_frame = self.text_drawer.draw_text_box(
                        select_frame, f"已选择 {len(markers)} 个标记", (20, 65),
                        font_size=12, text_color=(255, 255, 255)
                    )
                    select_frame = self.text_drawer.draw_text_box(
                        select_frame, "左键: 添加标记", (20, 90),
                        font_size=12, text_color=(255, 255, 255)
                    )
                    select_frame = self.text_drawer.draw_text_box(
                        select_frame, "右键: 删除上一个 | 空格: 完成 | ESC: 取消", 
                        (20, 115), font_size=12, text_color=(255, 255, 255)
                    )
                    
                    cv2.imshow("Select Markers", select_frame)
        
        cv2.namedWindow("Select Markers", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Select Markers", min(800, self.width), min(600, self.height))
        cv2.setMouseCallback("Select Markers", mouse_callback)
        
        # 初始绘制
        select_frame = self.text_drawer.draw_text_box(
            select_frame, "选择标志物", (20, 35),
            font_size=14, text_color=(255, 255, 255)
        )
        select_frame = self.text_drawer.draw_text_box(
            select_frame, "1. 左键点击视频中的标志物", (20, 65),
            font_size=12, text_color=(255, 255, 255)
        )
        select_frame = self.text_drawer.draw_text_box(
            select_frame, "2. 右键删除上一个标记", (20, 90),
            font_size=12, text_color=(255, 255, 255)
        )
        select_frame = self.text_drawer.draw_text_box(
            select_frame, "3. 按空格键完成，ESC取消", (20, 115),
            font_size=12, text_color=(255, 255, 255)
        )
        
        cv2.imshow("Select Markers", select_frame)
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == 32:  # 空格键
                break
            elif key == 27:  # ESC键
                cv2.destroyWindow("Select Markers")
                return False
        
        cv2.destroyWindow("Select Markers")
        
        if markers:
            self.tracking_points = markers
            if not self.initialize_optical_flow():
                messagebox.showwarning("警告", "无法初始化光流跟踪器")
                return False
            
            if messagebox.askyesno("确认", f"已选择 {len(markers)} 个标记。是否开始跟踪？"):
                print(f"已选择 {len(markers)} 个标志物")
                return True
            else:
                self.tracking_points = []
                return False
        
        return False
    
    def initialize_optical_flow(self):
        """初始化光流跟踪器"""
        if not self.tracking_points:
            return False
        
        # 初始化跟踪数据
        self.tracked_positions = {i: {'x': [], 'y': [], 'frame': []} 
                                 for i in range(len(self.tracking_points))}
        self.tracking_confidences = {i: [] for i in range(len(self.tracking_points))}
        self.low_confidence_frames = {i: [] for i in range(len(self.tracking_points))}
        self.position_history = {i: [] for i in range(len(self.tracking_points))}
        
        # 读取第一帧
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = self.cap.read()
        if not ret:
            print("无法读取视频帧")
            return False
        
        # 初始化光流跟踪器
        success = self.optical_flow_tracker.initialize(frame, self.tracking_points)
        if not success:
            print("光流跟踪器初始化失败")
            return False
        
        # 记录初始位置
        for i, point in enumerate(self.tracking_points):
            self.tracked_positions[i]['x'].append(point[0])
            self.tracked_positions[i]['y'].append(point[1])
            self.tracked_positions[i]['frame'].append(0)
            self.tracking_confidences[i].append(1.0)
            self.position_history[i].append(point)
        
        return True
    
    def recalibrate_marker(self, frame_idx, marker_id, new_position):
        """重新标记指定标记点并从该帧重新开始跟踪
        
        参数:
            frame_idx: 重新标记的帧索引
            marker_id: 标记点ID
            new_position: 新的位置 (x, y)
        """
        print(f"重新标记标记点 {marker_id+1} 在帧 {frame_idx}, 新位置: {new_position}")
        
        # 更新标记点在该帧的位置
        self.tracked_positions[marker_id]['x'][frame_idx] = new_position[0]
        self.tracked_positions[marker_id]['y'][frame_idx] = new_position[1]
        
        # 更新位置历史
        self.position_history[marker_id][frame_idx] = new_position
        
        # 设置重新标记的起始帧
        self.recalibration_start_frame = frame_idx
        
        # 重新初始化光流跟踪器
        ret = self.reinitialize_optical_flow_from_frame(frame_idx)
        
        return ret
    
    def reinitialize_optical_flow_from_frame(self, start_frame):
        """从指定帧重新初始化光流跟踪器"""
        # 获取指定帧的所有标记点位置
        current_positions = []
        for i in range(len(self.tracking_points)):
            if i in self.tracked_positions and len(self.tracked_positions[i]['x']) > start_frame:
                x = self.tracked_positions[i]['x'][start_frame]
                y = self.tracked_positions[i]['y'][start_frame]
                current_positions.append((x, y))
            else:
                # 如果没有该帧的数据，使用前一个可用的位置
                if self.tracked_positions[i]['x']:
                    x = self.tracked_positions[i]['x'][-1]
                    y = self.tracked_positions[i]['y'][-1]
                    current_positions.append((x, y))
                else:
                    current_positions.append(self.tracking_points[i])
        
        # 跳转到指定帧
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        ret, frame = self.cap.read()
        if not ret:
            print(f"无法读取帧 {start_frame}")
            return False
        
        # 重新初始化光流跟踪器
        success = self.optical_flow_tracker.initialize(frame, current_positions)
        
        if success:
            print(f"从帧 {start_frame} 重新初始化光流跟踪器成功")
            return True
        else:
            print(f"从帧 {start_frame} 重新初始化光流跟踪器失败")
            return False
    
    def adjust_recalibration_frame(self, current_frame_idx, direction):
        """调整重新标记的帧
        
        参数:
            current_frame_idx: 当前帧索引
            direction: 方向，1表示向前，-1表示向后
        
        返回:
            新的帧索引
        """
        new_frame_idx = current_frame_idx + direction
        
        # 确保帧索引在有效范围内
        if new_frame_idx < 0:
            new_frame_idx = 0
        elif new_frame_idx >= self.frame_count:
            new_frame_idx = self.frame_count - 1
        
        return new_frame_idx
    
    def draw_markers_on_frame(self, frame, frame_idx):
        """在指定帧上绘制标记点
        
        参数:
            frame: 视频帧
            frame_idx: 帧索引
        
        返回:
            带有标记点的帧
        """
        result = frame.copy()
        
        # 绘制所有标记点
        for i in range(len(self.tracking_points)):
            # 获取该帧的标记点位置
            if i in self.tracked_positions and len(self.tracked_positions[i]['x']) > frame_idx:
                x = self.tracked_positions[i]['x'][frame_idx]
                y = self.tracked_positions[i]['y'][frame_idx]
                
                # 绘制标记点
                color = self.colors[i % len(self.colors)]
                cv2.circle(result, (int(x), int(y)), 8, color, -1)
                cv2.circle(result, (int(x), int(y)), 10, (255, 255, 255), 2)
                cv2.putText(result, f"M{i+1}", (int(x)-15, int(y)-15),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        return result
    
    def update_recalibrate_display(self, frame, selected_marker, new_position, recalibration_frame_idx):
        """更新重新标记模式的显示"""
        display = frame.copy()
        
        # 绘制所有标记点
        for i in range(len(self.tracking_points)):
            if i in self.tracked_positions and len(self.tracked_positions[i]['x']) > recalibration_frame_idx:
                point_x = self.tracked_positions[i]['x'][recalibration_frame_idx]
                point_y = self.tracked_positions[i]['y'][recalibration_frame_idx]
                
                color = self.colors[i % len(self.colors)]
                # 如果是选中的标记点，用黄色高亮显示
                if i == selected_marker:
                    cv2.circle(display, (int(point_x), int(point_y)), 15, (0, 255, 255), 3)
                    cv2.circle(display, (int(point_x), int(point_y)), 17, (255, 255, 255), 1)
                else:
                    cv2.circle(display, (int(point_x), int(point_y)), 8, color, -1)
                    cv2.circle(display, (int(point_x), int(point_y)), 10, (255, 255, 255), 2)
                
                cv2.putText(display, f"M{i+1}", (int(point_x)-15, int(point_y)-15),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # 如果设置了新位置，绘制新位置
        if new_position is not None:
            cv2.circle(display, (int(new_position[0]), int(new_position[1])), 8, (0, 255, 255), -1)
            cv2.circle(display, (int(new_position[0]), int(new_position[1])), 10, (255, 255, 255), 2)
            cv2.putText(display, "New", (int(new_position[0])-10, int(new_position[1])-20),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        return display
    
    def track_markers(self):
        """开始跟踪标志物 (已修复鼠标交互版本)"""
        if not self.tracking_points:
            messagebox.showwarning("警告", "请先选择标志物")
            return
        
        self.tracking_active = True
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        cv2.namedWindow("Tracking", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Tracking", min(800, self.width), min(600, self.height))
        
        # 初始化状态变量
        frame_idx = 0
        paused = False
        recalibrating = False
        selected_marker = None
        new_position = None
        recalibration_frame_idx = 0
        
        # 用于重新标记的当前显示帧
        recalibrate_frame_display = None
        
        def mouse_callback(event, x, y, flags, param):
            """重新标记模式下的鼠标回调函数"""
            nonlocal selected_marker, new_position, recalibrate_frame_display
            
            if not recalibrating:
                return
            
            if event == cv2.EVENT_LBUTTONDOWN:
                print(f"鼠标点击位置: ({x}, {y})")
                
                if selected_marker is None:
                    # 第一步：选择要重新标记的点
                    min_dist = float('inf')
                    closest_marker = None
                    
                    # 在当前帧上查找最近的标记点
                    for i in range(len(self.tracking_points)):
                        # 获取该帧的标记点位置
                        if (i in self.tracked_positions and 
                            len(self.tracked_positions[i]['x']) > recalibration_frame_idx):
                            point_x = self.tracked_positions[i]['x'][recalibration_frame_idx]
                            point_y = self.tracked_positions[i]['y'][recalibration_frame_idx]
                        else:
                            # 如果还没有该帧的数据，跳过
                            continue
                        
                        # 计算鼠标点击位置与标记点的距离
                        dist = np.sqrt((x - point_x)**2 + (y - point_y)**2)
                        # 如果距离在30像素内，并且是最小的
                        if dist < 30 and dist < min_dist:
                            min_dist = dist
                            closest_marker = i
                    
                    if closest_marker is not None:
                        selected_marker = closest_marker
                        print(f"✓ 选择了标记点 {selected_marker+1} 进行重新标记")
                        # 刷新显示，高亮选中的点
                        if recalibrate_frame_display is not None:
                            display = self.update_recalibrate_display(
                                recalibrate_frame_display, selected_marker, new_position, recalibration_frame_idx)
                            cv2.imshow("Tracking", display)
                    else:
                        print("未找到附近的标记点，请点击标记点附近")
                else:
                    # 第二步：设置新位置
                    new_position = (x, y)
                    print(f"✓ 为标记点 {selected_marker+1} 设置新位置: {new_position}")
                    # 刷新显示，显示新位置
                    if recalibrate_frame_display is not None:
                        display = self.update_recalibrate_display(
                            recalibrate_frame_display, selected_marker, new_position, recalibration_frame_idx)
                        cv2.imshow("Tracking", display)
        
        # 设置鼠标回调函数
        cv2.setMouseCallback("Tracking", mouse_callback)
        
        print("开始光流跟踪...")
        print("控制说明:")
        print("  ESC: 停止跟踪")
        print("  P: 暂停/继续")
        print("  R: 进入重新标记模式")
        
        # 主循环
        while True:
            # 正常跟踪模式
            if not paused and not recalibrating:
                ret, frame = self.cap.read()
                if not ret:
                    print("视频结束")
                    break
                
                # 更新光流跟踪
                success, points = self.optical_flow_tracker.update(frame)
                
                if success:
                    current_points = self.optical_flow_tracker.get_points()
                    current_status = self.optical_flow_tracker.get_status()
                    
                    for i in range(len(self.tracking_points)):
                        if current_status[i] and current_points[i] is not None:
                            x, y = current_points[i]
                            
                            # 计算置信度
                            if i in self.position_history and len(self.position_history[i]) > 0:
                                last_x, last_y = self.position_history[i][-1]
                                distance = np.sqrt((x - last_x)**2 + (y - last_y)**2)
                                confidence = max(0.3, min(1.0, 1.0 - distance/50))
                            else:
                                confidence = 1.0
                            
                            # 更新数据
                            self.tracked_positions[i]['x'].append(x)
                            self.tracked_positions[i]['y'].append(y)
                            self.tracked_positions[i]['frame'].append(frame_idx)
                            self.tracking_confidences[i].append(confidence)
                            self.position_history[i].append((x, y))
                
                frame_idx += 1
                
                # 创建显示帧
                display_frame = frame.copy()
                
                # 绘制当前跟踪点
                if 'current_points' in locals():
                    for i in range(len(self.tracking_points)):
                        if i in current_points and current_points[i] is not None:
                            x, y = current_points[i]
                            color = self.colors[i % len(self.colors)]
                            cv2.circle(display_frame, (int(x), int(y)), 8, color, -1)
                            cv2.circle(display_frame, (int(x), int(y)), 10, (255, 255, 255), 2)
                            cv2.putText(display_frame, f"M{i+1}", (int(x)-15, int(y)-15),
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                
                # 显示信息框
                cv2.rectangle(display_frame, (10, 10), (350, 180), (0, 0, 0), -1)
                cv2.rectangle(display_frame, (10, 10), (350, 180), (255, 255, 255), 1)
                
                # 使用中文文本绘制器显示状态信息
                display_frame = self.text_drawer.put_chinese_text(
                    display_frame, f"帧: {frame_idx}/{self.frame_count}", (20, 35),
                    font_size=14, color=(255, 255, 255)
                )
                display_frame = self.text_drawer.put_chinese_text(
                    display_frame, f"标记数: {len(self.tracking_points)}", (20, 60),
                    font_size=14, color=(255, 255, 255)
                )
                
                # 显示当前跟踪置信度
                conf_y = 85
                for i in range(min(len(self.tracking_points), 5)):  # 最多显示5个标记
                    if i in self.tracking_confidences and self.tracking_confidences[i]:
                        last_conf = self.tracking_confidences[i][-1] if len(self.tracking_confidences[i]) > 0 else 0
                        color = (0, 255, 0) if last_conf >= self.confidence_threshold else (0, 0, 255)
                        cv2.putText(display_frame, f"M{i+1}: {last_conf:.2f}", (20, conf_y),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                        conf_y += 15
                
                if paused:
                    display_frame = self.text_drawer.put_chinese_text(
                        display_frame, "已暂停 - 按P继续", (self.width-200, 30),
                        font_size=14, color=(0, 255, 255)
                    )
                
                # 控制提示使用英文（避免中文显示问题）
                cv2.putText(display_frame, "ESC:Stop P:Pause/Resume R:Recalibrate", 
                           (10, self.height-20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                
                cv2.imshow("Tracking", display_frame)
            
            # 重新标记模式
            elif recalibrating:
                # 读取重新标记的帧
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, recalibration_frame_idx)
                ret, frame = self.cap.read()
                if not ret:
                    print(f"无法读取帧 {recalibration_frame_idx}")
                    break
                
                # 更新显示帧
                recalibrate_frame_display = frame.copy()
                display = self.update_recalibrate_display(
                    recalibrate_frame_display, selected_marker, new_position, recalibration_frame_idx)
                
                # 添加重新标记模式的信息显示
                cv2.rectangle(display, (10, 10), (400, 200), (0, 0, 0), -1)
                cv2.rectangle(display, (10, 10), (400, 200), (255, 255, 255), 1)
                
                display = self.text_drawer.put_chinese_text(
                    display, "重新标记模式", (20, 35),
                    font_size=14, color=(0, 255, 255)
                )
                display = self.text_drawer.put_chinese_text(
                    display, f"当前帧: {recalibration_frame_idx}", (20, 60),
                    font_size=12, color=(255, 255, 255)
                )
                
                if selected_marker is not None:
                    display = self.text_drawer.put_chinese_text(
                        display, f"已选择标记 {selected_marker+1}", (20, 85),
                        font_size=12, color=(0, 255, 255)
                    )
                
                if new_position is not None:
                    display = self.text_drawer.put_chinese_text(
                        display, f"新位置已设置", (20, 110),
                        font_size=12, color=(0, 255, 255)
                    )
                
                # 操作提示
                display = self.text_drawer.put_chinese_text(
                    display, "操作说明:", (20, self.height-140),
                    font_size=12, color=(0, 255, 255)
                )
                display = self.text_drawer.put_chinese_text(
                    display, "左键点击标记点选择", (20, self.height-120),
                    font_size=10, color=(255, 255, 255)
                )
                display = self.text_drawer.put_chinese_text(
                    display, "左键点击新位置设置", (20, self.height-100),
                    font_size=10, color=(255, 255, 255)
                )
                display = self.text_drawer.put_chinese_text(
                    display, "A/D键: 前一帧/后一帧", (20, self.height-80),
                    font_size=10, color=(255, 255, 255)
                )
                display = self.text_drawer.put_chinese_text(
                    display, "Enter: 确认并继续跟踪", (20, self.height-60),
                    font_size=10, color=(255, 255, 255)
                )
                display = self.text_drawer.put_chinese_text(
                    display, "ESC: 取消重新标记", (20, self.height-40),
                    font_size=10, color=(255, 255, 255)
                )
                
                cv2.imshow("Tracking", display)
            
            # 键盘事件处理
            wait_time = 0 if (paused or recalibrating) else 1
            key = cv2.waitKey(wait_time) & 0xFF
            
            if key == 27:  # ESC键
                if recalibrating:
                    # 取消重新标记
                    recalibrating = False
                    selected_marker = None
                    new_position = None
                    print("取消重新标记")
                else:
                    print("用户停止跟踪")
                    break
            
            elif key == ord('p') or key == ord('P'):
                paused = not paused
                print("已暂停" if paused else "继续跟踪")
            
            elif key == ord('r') or key == ord('R'):
                # 进入重新标记模式
                if not recalibrating:
                    recalibrating = True
                    paused = True
                    recalibration_frame_idx = max(0, frame_idx - 1)
                    selected_marker = None
                    new_position = None
                    print(f"进入重新标记模式，当前帧: {recalibration_frame_idx}")
                    print("1. 左键点击要修正的标记点")
                    print("2. 左键点击新位置")
                    print("3. 按A/D切换帧，按Enter确认")
                else:
                    # 如果已经在重新标记模式，可以按R退出
                    recalibrating = False
                    selected_marker = None
                    new_position = None
                    print("退出重新标记模式")
            
            # A/D键：在重新标记模式下切换帧
            elif recalibrating and (key == ord('a') or key == ord('A')):
                recalibration_frame_idx = max(0, recalibration_frame_idx - 1)
                selected_marker = None
                new_position = None
                print(f"切换到前一帧: {recalibration_frame_idx}")
            
            elif recalibrating and (key == ord('d') or key == ord('D')):
                recalibration_frame_idx = min(self.frame_count - 1, recalibration_frame_idx + 1)
                selected_marker = None
                new_position = None
                print(f"切换到后一帧: {recalibration_frame_idx}")
            
            # Enter键：确认重新标记
            elif key == 13 and recalibrating and selected_marker is not None and new_position is not None:
                # 执行重新标记
                success = self.recalibrate_marker(recalibration_frame_idx, selected_marker, new_position)
                if success:
                    # 从重新标记的帧开始继续跟踪
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.recalibration_start_frame)
                    frame_idx = self.recalibration_start_frame
                    paused = False
                    recalibrating = False
                    selected_marker = None
                    new_position = None
                    print(f"重新标记完成，从帧 {frame_idx} 继续跟踪")
                else:
                    print("重新标记失败，请重试")
        
        cv2.destroyWindow("Tracking")
        self.tracking_active = False
        print(f"跟踪完成，处理了 {frame_idx} 帧")
        self.generate_quality_report()
    
    def generate_quality_report(self):
        """生成跟踪质量报告"""
        if not self.tracking_confidences:
            print("没有跟踪置信度数据")
            return
        
        print("\n" + "="*50)
        print("跟踪质量报告")
        print("="*50)
        
        for marker_id in range(len(self.tracking_points)):
            if marker_id in self.tracking_confidences and self.tracking_confidences[marker_id]:
                confidences = self.tracking_confidences[marker_id]
                if confidences:
                    avg_confidence = np.mean(confidences)
                    low_confidence_count = sum(1 for c in confidences if c < self.confidence_threshold)
                    low_confidence_percent = (low_confidence_count / len(confidences)) * 100
                    
                    print(f"标记 {marker_id+1}:")
                    print(f"  平均置信度: {avg_confidence:.3f}")
                    print(f"  低置信度帧数: {low_confidence_count}/{len(confidences)} ({low_confidence_percent:.1f}%)")
                    print(f"  跟踪方法: 光流法")
                    print()
    
    def smooth_positions(self, positions, window_size=5):
        """使用移动平均平滑位置数据"""
        if len(positions) < window_size:
            return positions
        
        smoothed = []
        for i in range(len(positions)):
            start_idx = max(0, i - window_size // 2)
            end_idx = min(len(positions), i + window_size // 2 + 1)
            window = positions[start_idx:end_idx]
            smoothed.append(np.mean(window))
        
        return smoothed
    
    def convert_to_cm(self):
        """将像素坐标转换为厘米坐标"""
        if not self.tracked_positions:
            return {}
        
        cm_coords = {}
        for marker_id, data in self.tracked_positions.items():
            if not data['x']:
                continue
            
            x_smoothed = self.smooth_positions(data['x'], self.smoothing_window)
            y_smoothed = self.smooth_positions(data['y'], self.smoothing_window)
            
            cm_coords[marker_id] = {
                'x_px': data['x'],
                'y_px': data['y'],
                'x_px_smooth': x_smoothed,
                'y_px_smooth': y_smoothed,
                'x_cm': [x * self.scale_factor for x in x_smoothed],
                'y_cm': [y * self.scale_factor for y in y_smoothed],
                'frame': data['frame']
            }
        
        return cm_coords
    
    def calculate_kinematics(self, cm_coords):
        """计算运动学参数"""
        kinematics = {}
        
        for marker_id, data in cm_coords.items():
            if len(data['x_cm']) < 2:
                continue
            
            time = np.array(data['frame']) / self.fps
            displacement_x = np.array(data['x_cm']) - data['x_cm'][0]
            displacement_y = np.array(data['y_cm']) - data['y_cm'][0]
            displacement_mag = np.sqrt(displacement_x**2 + displacement_y**2)
            
            vx = np.gradient(data['x_cm'], time)
            vy = np.gradient(data['y_cm'], time)
            v_mag = np.sqrt(vx**2 + vy**2)
            
            if len(time) > 2:
                ax = np.gradient(vx, time)
                ay = np.gradient(vy, time)
                a_mag = np.sqrt(ax**2 + ay**2)
            else:
                ax = np.zeros_like(vx)
                ay = np.zeros_like(vy)
                a_mag = np.zeros_like(v_mag)
            
            kinematics[marker_id] = {
                'time': time,
                'displacement_x': displacement_x,
                'displacement_y': displacement_y,
                'displacement_mag': displacement_mag,
                'vx': vx,
                'vy': vy,
                'v_mag': v_mag,
                'ax': ax,
                'ay': ay,
                'a_mag': a_mag
            }
        
        return kinematics
    
    def calculate_damping_coefficient(self, marker_id, start_frame=None, end_frame=None):
        """计算标记点的阻尼系数

        参数:
            marker_id: 标记点ID
            start_frame: 起始帧号，如果为None则使用第一帧
            end_frame: 结束帧号，如果为None则使用最后一帧

        返回:
            damping_coefficient: 阻尼系数
            equilibrium_position: 平衡位置(y0)
            r_squared: 拟合优度
        """
        if marker_id not in self.tracked_positions:
            return None, None, None

        # 获取位置数据
        positions = self.tracked_positions[marker_id]
        if len(positions['x']) < 3:
            return None, None, None

        # 转换为厘米
        cm_coords = self.convert_to_cm()
        if marker_id not in cm_coords:
            return None, None, None

        # 获取时间、位置和速度数据
        time = np.array(cm_coords[marker_id]['frame']) / self.fps
        x = np.array(cm_coords[marker_id]['x_cm'])
        y = np.array(cm_coords[marker_id]['y_cm'])

        # 计算y方向位移（只分析垂直方向的阻尼）
        displacement = y - y[0]

        # 确定分析的帧范围
        start_idx = 0
        end_idx = len(time) - 1

        if start_frame is not None:
            start_idx = max(0, min(start_frame, len(time) - 1))
        if end_frame is not None:
            end_idx = max(start_idx, min(end_frame, len(time) - 1))

        # 提取子范围数据
        time_segment = time[start_idx:end_idx+1]
        displacement_segment = displacement[start_idx:end_idx+1]

        # 初始猜测
        A_guess = displacement_segment[0] - displacement_segment[-1] if displacement_segment[0] != displacement_segment[-1] else 1.0
        b_guess = 0.1  # 初始阻尼系数猜测
        y0_guess = displacement_segment[-1]  # 初始平衡位置猜测

        # 尝试拟合
        try:
            # 将时间归一化，从0开始
            t_norm = time_segment - time_segment[0]

            # 执行拟合
            popt, pcov = curve_fit(damping_model, t_norm, displacement_segment, 
                                  p0=[A_guess, b_guess, y0_guess], maxfev=10000)

            # 计算拟合优度
            residuals = displacement_segment - damping_model(t_norm, *popt)
            ss_res = np.sum(residuals**2)
            ss_tot = np.sum((displacement_segment - np.mean(displacement_segment))**2)
            r_squared = 1 - (ss_res / ss_tot)

            # 返回阻尼系数、平衡位置和拟合优度
            return popt[1], popt[2], r_squared

        except Exception as e:
            print(f"计算阻尼系数时出错: {e}")
            return None, None, None

    def select_damping_segment(self, marker_id):
        """交互式选择阻尼系数计算的帧范围

        参数:
            marker_id: 要分析的标记点ID

        返回:
            (start_frame, end_frame): 选择的帧范围
        """
        if marker_id not in self.tracked_positions:
            print("标记点数据不存在")
            return None, None

        # 获取位置数据
        positions = self.tracked_positions[marker_id]
        if len(positions['x']) < 3:
            print("数据点不足，无法计算阻尼系数")
            return None, None

        # 转换为厘米
        cm_coords = self.convert_to_cm()
        if marker_id not in cm_coords:
            print("无法获取厘米坐标数据")
            return None, None

        # 获取数据
        time = np.array(cm_coords[marker_id]['frame']) / self.fps
        x = np.array(cm_coords[marker_id]['x_cm'])
        y = np.array(cm_coords[marker_id]['y_cm'])

        # 计算y方向位移（只分析垂直方向的阻尼）
        displacement = y - y[0]

        # 创建交互式图表
        fig, ax = plt.subplots(figsize=(10, 6))
        line, = ax.plot(time, displacement, 'b-', label='位移')
        vline_start = ax.axvline(x=time[0], color='r', linestyle='--', label='起始帧')
        vline_end = ax.axvline(x=time[-1], color='g', linestyle='--', label='结束帧')

        ax.set_xlabel('时间 (s)')
        ax.set_ylabel('位移 (cm)')
        ax.set_title(f'标记点 {marker_id+1} 位移曲线 - 选择阻尼分析范围')
        ax.grid(True)
        ax.legend()

        # 存储选择的帧
        selected_frames = [0, len(time)-1]

        def on_click(event):
            if event.inaxes != ax:
                return

            # 找到最近的时间点
            click_time = event.xdata
            idx = np.argmin(np.abs(time - click_time))

            # 判断是左键还是右键
            if event.button == 1:  # 左键 - 设置起始点
                selected_frames[0] = idx
                vline_start.set_xdata([time[idx]])
            elif event.button == 3:  # 右键 - 设置结束点
                selected_frames[1] = idx
                vline_end.set_xdata([time[idx]])

            fig.canvas.draw()

        def on_key(event):
            if event.key == 'enter':  # 按Enter键确认选择
                plt.close(fig)
            elif event.key == 'escape':  # 按ESC键取消
                selected_frames[0] = None
                selected_frames[1] = None
                plt.close(fig)

        # 连接事件
        fig.canvas.mpl_connect('button_press_event', on_click)
        fig.canvas.mpl_connect('key_press_event', on_key)

        # 显示提示
        print("\n选择阻尼分析范围:")
        print("  左键点击: 设置起始点")
        print("  右键点击: 设置结束点")
        print("  Enter键: 确认选择")
        print("  ESC键: 取消选择")

        plt.show()

        # 返回选择的帧
        if selected_frames[0] is not None and selected_frames[1] is not None:
            return selected_frames[0], selected_frames[1]
        return None, None

    def analyze_damping(self):
        """分析所有标记点的阻尼系数"""
        if not self.tracked_positions:
            messagebox.showwarning("警告", "没有跟踪数据可分析")
            return

        print("\n开始阻尼系数分析...")

        # 为每个标记点选择分析范围
        for marker_id in range(len(self.tracking_points)):
            if marker_id not in self.tracked_positions:
                continue

            print(f"\n分析标记点 {marker_id+1}")
            start_frame, end_frame = self.select_damping_segment(marker_id)

            if start_frame is not None and end_frame is not None:
                # 计算阻尼系数
                damping_coeff, equilibrium_pos, r_squared = self.calculate_damping_coefficient(
                    marker_id, start_frame, end_frame)

                if damping_coeff is not None:
                    # 存储结果
                    if marker_id not in self.damping_coefficients:
                        self.damping_coefficients[marker_id] = []

                    self.damping_coefficients[marker_id].append({
                        'start_frame': start_frame,
                        'end_frame': end_frame,
                        'damping_coefficient': damping_coeff,
                        'equilibrium_position': equilibrium_pos,
                        'r_squared': r_squared
                    })

                    # 存储段信息
                    if marker_id not in self.damping_segments:
                        self.damping_segments[marker_id] = []

                    self.damping_segments[marker_id].append((start_frame, end_frame))

                    print(f"  阻尼系数: {damping_coeff:.4f}")
                    print(f"  平衡位置: {equilibrium_pos:.4f}")
                    print(f"  拟合优度 (R²): {r_squared:.4f}")
                else:
                    print("  无法计算阻尼系数")
            else:
                print("  未选择分析范围")

        print("\n阻尼系数分析完成")
        self.plot_damping_results()

    def plot_damping_results(self):
        """绘制阻尼系数分析结果"""
        if not self.damping_coefficients:
            messagebox.showwarning("警告", "没有阻尼系数数据可绘制")
            return

        # 获取厘米坐标数据
        cm_coords = self.convert_to_cm()

        # 创建图表
        fig = plt.figure(figsize=(16, 12))

        try:
            # 为每个标记点创建子图
            marker_count = len(self.damping_coefficients)
            rows = (marker_count + 1) // 2  # 每行2个子图

            for idx, (marker_id, damping_data) in enumerate(self.damping_coefficients.items()):
                if marker_id not in cm_coords:
                    continue

                # 创建子图
                ax = plt.subplot(rows, 2, idx+1)

                # 获取数据
                time = np.array(cm_coords[marker_id]['frame']) / self.fps
                x = np.array(cm_coords[marker_id]['x_cm'])
                y = np.array(cm_coords[marker_id]['y_cm'])

                # 计算y方向位移（只分析垂直方向的阻尼）
                displacement = y - y[0]

                # 绘制原始位移曲线
                color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                ax.plot(time, displacement, '-', color=color, alpha=0.7, label='位移')

                # 为每个阻尼段绘制拟合曲线
                for segment in damping_data:
                    start_frame = segment['start_frame']
                    end_frame = segment['end_frame']
                    damping_coeff = segment['damping_coefficient']
                    equilibrium_pos = segment['equilibrium_position']
                    r_squared = segment['r_squared']

                    # 提取段数据
                    time_segment = time[start_frame:end_frame+1]
                    displacement_segment = displacement[start_frame:end_frame+1]

                    # 归一化时间
                    t_norm = time_segment - time_segment[0]

                    # 拟合曲线
                    A_guess = displacement_segment[0] - displacement_segment[-1] if displacement_segment[0] != displacement_segment[-1] else 1.0
                    try:
                        fit_curve = damping_model(t_norm, A_guess, damping_coeff, equilibrium_pos)
                        ax.plot(time_segment, fit_curve, '--', color=color, 
                               label=f'阻尼拟合 (b={damping_coeff:.4f}, y0={equilibrium_pos:.2f}, R²={r_squared:.3f})')

                        # 高亮显示段范围
                        ax.axvspan(time_segment[0], time_segment[-1], alpha=0.2, color=color)
                    except:
                        pass

                ax.set_xlabel('时间 (s)')
                ax.set_ylabel('位移 (cm)')
                ax.set_title(f'标记点 {marker_id+1} 阻尼分析')
                ax.grid(True, alpha=0.3)
                ax.legend(fontsize='small')

            plt.suptitle('阻尼系数分析结果', fontsize=16, fontweight='bold')
            plt.tight_layout()
            plt.show()

        except Exception as e:
            print(f"绘制阻尼系数图表时出错: {e}")
            messagebox.showerror("错误", f"绘制阻尼系数图表时出错: {e}")

    def plot_results(self):
        """绘制详细的分析结果"""
        if not self.tracked_positions:
            messagebox.showwarning("警告", "没有跟踪数据可绘制")
            return
        
        cm_coords = self.convert_to_cm()
        if not cm_coords:
            messagebox.showwarning("警告", "没有有效的跟踪数据")
            return
        
        kinematics = self.calculate_kinematics(cm_coords)
        
        fig = plt.figure(figsize=(16, 12))
        
        try:
            # 1. 原始轨迹对比
            ax1 = plt.subplot(3, 3, 1)
            for marker_id, data in cm_coords.items():
                color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                ax1.plot(data['x_px'], data['y_px'], '-', color=color, alpha=0.3, label=f'原始 {marker_id+1}')
                ax1.plot(data['x_px_smooth'], data['y_px_smooth'], '-', color=color, linewidth=2, label=f'平滑 {marker_id+1}')
                ax1.plot(data['x_px_smooth'][0], data['y_px_smooth'][0], 'o', color=color, markersize=8)
                ax1.plot(data['x_px_smooth'][-1], data['y_px_smooth'][-1], 's', color=color, markersize=8)
            ax1.set_title('轨迹对比（平滑前后）')
            ax1.set_xlabel('X (像素)')
            ax1.set_ylabel('Y (像素)')
            ax1.legend(fontsize='small')
            ax1.grid(True, alpha=0.3)
            ax1.invert_yaxis()
            
            # 2. 实际轨迹（厘米）
            ax2 = plt.subplot(3, 3, 2)
            for marker_id, data in cm_coords.items():
                color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                ax2.plot(data['x_cm'], data['y_cm'], '-', color=color, linewidth=2, label=f'标记 {marker_id+1}')
                ax2.plot(data['x_cm'][0], data['y_cm'][0], 'o', color=color, markersize=8)
                ax2.plot(data['x_cm'][-1], data['y_cm'][-1], 's', color=color, markersize=8)
            ax2.set_title('实际轨迹（厘米）')
            ax2.set_xlabel('X (cm)')
            ax2.set_ylabel('Y (cm)')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            ax2.invert_yaxis()
            
            # 3. X方向位移-时间
            ax3 = plt.subplot(3, 3, 4)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    ax3.plot(kinematics[marker_id]['time'], kinematics[marker_id]['displacement_x'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            ax3.set_title('X方向位移')
            ax3.set_xlabel('时间 (s)')
            ax3.set_ylabel('X位移 (cm)')
            ax3.legend()
            ax3.grid(True, alpha=0.3)
            
            # 4. Y方向位移-时间
            ax4 = plt.subplot(3, 3, 5)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    ax4.plot(kinematics[marker_id]['time'], kinematics[marker_id]['displacement_y'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            ax4.set_title('Y方向位移')
            ax4.set_xlabel('时间 (s)')
            ax4.set_ylabel('Y位移 (cm)')
            ax4.legend()
            ax4.grid(True, alpha=0.3)
            
            # 5. 总位移-时间
            ax5 = plt.subplot(3, 3, 6)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    ax5.plot(kinematics[marker_id]['time'], kinematics[marker_id]['displacement_mag'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            ax5.set_title('总位移')
            ax5.set_xlabel('时间 (s)')
            ax5.set_ylabel('位移大小 (cm)')
            ax5.legend()
            ax5.grid(True, alpha=0.3)
            
            # 6. 速度-时间
            ax6 = plt.subplot(3, 3, 7)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    ax6.plot(kinematics[marker_id]['time'], kinematics[marker_id]['v_mag'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            ax6.set_title('速度大小')
            ax6.set_xlabel('时间 (s)')
            ax6.set_ylabel('速度 (cm/s)')
            ax6.legend()
            ax6.grid(True, alpha=0.3)
            
            # 7. 加速度-时间
            ax7 = plt.subplot(3, 3, 8)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    ax7.plot(kinematics[marker_id]['time'], kinematics[marker_id]['a_mag'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            ax7.set_title('加速度大小')
            ax7.set_xlabel('时间 (s)')
            ax7.set_ylabel('加速度 (cm/s²)')
            ax7.legend()
            ax7.grid(True, alpha=0.3)
            
            # 8. 置信度分析
            ax8 = plt.subplot(3, 3, 3)
            for marker_id in self.tracking_confidences:
                if self.tracking_confidences[marker_id]:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    frames = list(range(len(self.tracking_confidences[marker_id])))
                    ax8.plot(frames, self.tracking_confidences[marker_id], 
                            '-', color=color, alpha=0.6, label=f'标记 {marker_id+1}')
            
            ax8.axhline(y=self.confidence_threshold, color='r', linestyle='--', alpha=0.5, label='置信度阈值')
            ax8.set_title('跟踪置信度')
            ax8.set_xlabel('帧')
            ax8.set_ylabel('置信度')
            ax8.legend(fontsize='small')
            ax8.grid(True, alpha=0.3)
            ax8.set_ylim(0, 1.1)
            
            # 9. 统计信息
            ax9 = plt.subplot(3, 3, 9)
            ax9.axis('off')
            
            stats_text = f'跟踪统计信息:\n\n'
            stats_text += f'视频文件: {os.path.basename(self.video_path)}\n'
            stats_text += f'总帧数: {self.frame_count}\n'
            stats_text += f'帧率: {self.fps:.1f} FPS\n'
            stats_text += f'时长: {self.frame_count/self.fps:.1f} s\n'
            stats_text += f'标度: 1像素 = {self.scale_factor:.4f} cm\n'
            stats_text += f'跟踪点数: {len(self.tracking_points)}\n'
            stats_text += f'跟踪算法: 光流法\n'
            stats_text += f'置信度阈值: {self.confidence_threshold}\n'
            
            for marker_id in range(len(self.tracking_points)):
                if marker_id in self.tracking_confidences and self.tracking_confidences[marker_id]:
                    confidences = self.tracking_confidences[marker_id]
                    avg_conf = np.mean(confidences)
                    low_conf_count = sum(1 for c in confidences if c < self.confidence_threshold)
                    low_conf_percent = (low_conf_count / len(confidences)) * 100
                    
                    stats_text += f'\n标记 {marker_id+1}:\n'
                    stats_text += f'  平均置信度: {avg_conf:.3f}\n'
                    stats_text += f'  低置信度: {low_conf_percent:.1f}%\n'
            
            ax9.text(0.1, 0.5, stats_text, fontsize=9, verticalalignment='center',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
            
            plt.suptitle('视频跟踪分析结果', fontsize=16, fontweight='bold')
            plt.tight_layout()
            plt.show()
            
        except Exception as e:
            print(f"绘制图表时出错: {e}")
            messagebox.showerror("错误", f"绘制图表时出错: {e}")
    
    def save_results(self, filename=None):
        """保存详细结果"""
        if not self.tracked_positions:
            messagebox.showwarning("警告", "没有数据可保存")
            return
        
        if filename is None:
            root = tk.Tk()
            root.withdraw()
            filename = filedialog.asksaveasfilename(
                title="保存结果",
                defaultextension=".xlsx",
                filetypes=[
                    ("Excel文件", "*.xlsx"),
                    ("CSV文件", "*.csv"),
                    ("JSON文件", "*.json"),
                    ("所有文件", "*.*")
                ]
            )
        
        if not filename:
            return
        
        # 创建结果文件夹
        base_name = os.path.splitext(os.path.basename(filename))[0]
        result_dir = os.path.join(os.path.dirname(filename), f"{base_name}_results")
        os.makedirs(result_dir, exist_ok=True)
        
        cm_coords = self.convert_to_cm()
        kinematics = self.calculate_kinematics(cm_coords)
        
        try:
            # 保存数据文件
            if filename.endswith('.xlsx'):
                with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                    all_data = []
                    for marker_id in cm_coords.keys():
                        for i in range(len(cm_coords[marker_id]['frame'])):
                            row = {
                                '标记ID': marker_id + 1,
                                '帧号': cm_coords[marker_id]['frame'][i],
                                '时间_s': cm_coords[marker_id]['frame'][i] / self.fps,
                                'X_像素': self.tracked_positions[marker_id]['x'][i],
                                'Y_像素': self.tracked_positions[marker_id]['y'][i],
                                'X_像素_平滑': cm_coords[marker_id]['x_px_smooth'][i],
                                'Y_像素_平滑': cm_coords[marker_id]['y_px_smooth'][i],
                                'X_cm': cm_coords[marker_id]['x_cm'][i],
                                'Y_cm': cm_coords[marker_id]['y_cm'][i]
                            }
                            
                            if marker_id in kinematics:
                                kin = kinematics[marker_id]
                                if i < len(kin['time']):
                                    row.update({
                                        'X位移_cm': kin['displacement_x'][i],
                                        'Y位移_cm': kin['displacement_y'][i],
                                        '总位移_cm': kin['displacement_mag'][i],
                                        'X速度_cm/s': kin['vx'][i],
                                        'Y速度_cm/s': kin['vy'][i],
                                        '速度大小_cm/s': kin['v_mag'][i],
                                    })
                            
                            if marker_id in self.tracking_confidences and i < len(self.tracking_confidences[marker_id]):
                                row['置信度'] = self.tracking_confidences[marker_id][i]
                            
                            all_data.append(row)
                    
                    df_data = pd.DataFrame(all_data)
                    df_data.to_excel(writer, sheet_name='跟踪数据', index=False)
                    
                    stats_data = {
                        '参数': ['视频文件', '总帧数', '帧率(FPS)', '时长(s)', '像素/cm比例', '跟踪点数', '置信度阈值', '跟踪算法'],
                        '值': [
                            os.path.basename(self.video_path),
                            self.frame_count,
                            f"{self.fps:.1f}",
                            f"{self.frame_count/self.fps:.1f}",
                            f"{self.scale_factor:.4f}",
                            len(self.tracking_points),
                            self.confidence_threshold,
                            "光流法"
                        ]
                    }
                    df_stats = pd.DataFrame(stats_data)
                    df_stats.to_excel(writer, sheet_name='统计信息', index=False)
                    
                    confidence_data = []
                    for marker_id in self.tracking_confidences:
                        confidences = self.tracking_confidences[marker_id]
                        for i, conf in enumerate(confidences):
                            confidence_data.append({
                                '标记ID': marker_id + 1,
                                '帧号': i,
                                '置信度': conf,
                                '是否低置信度': '是' if conf < self.confidence_threshold else '否'
                            })
                    
                    if confidence_data:
                        df_conf = pd.DataFrame(confidence_data)
                        df_conf.to_excel(writer, sheet_name='置信度分析', index=False)
                
                print(f"结果已保存到Excel文件: {filename}")
            
            # 保存单独的图像
            print("\n正在保存图像分析结果...")
            
            # 1. 轨迹对比图
            fig1 = plt.figure(figsize=(10, 8))
            for marker_id, data in cm_coords.items():
                color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                plt.plot(data['x_px'], data['y_px'], '-', color=color, alpha=0.3, label=f'原始 {marker_id+1}')
                plt.plot(data['x_px_smooth'], data['y_px_smooth'], '-', color=color, linewidth=2, label=f'平滑 {marker_id+1}')
                plt.plot(data['x_px_smooth'][0], data['y_px_smooth'][0], 'o', color=color, markersize=8)
                plt.plot(data['x_px_smooth'][-1], data['y_px_smooth'][-1], 's', color=color, markersize=8)
            plt.title('轨迹对比（平滑前后）')
            plt.xlabel('X (像素)')
            plt.ylabel('Y (像素)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.gca().invert_yaxis()
            plt.savefig(os.path.join(result_dir, '01_轨迹对比.png'), dpi=300, bbox_inches='tight')
            plt.close()
            
            # 2. 实际轨迹图
            fig2 = plt.figure(figsize=(10, 8))
            for marker_id, data in cm_coords.items():
                color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                plt.plot(data['x_cm'], data['y_cm'], '-', color=color, linewidth=2, label=f'标记 {marker_id+1}')
                plt.plot(data['x_cm'][0], data['y_cm'][0], 'o', color=color, markersize=8)
                plt.plot(data['x_cm'][-1], data['y_cm'][-1], 's', color=color, markersize=8)
            plt.title('实际轨迹（厘米）')
            plt.xlabel('X (cm)')
            plt.ylabel('Y (cm)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.gca().invert_yaxis()
            plt.savefig(os.path.join(result_dir, '02_实际轨迹.png'), dpi=300, bbox_inches='tight')
            plt.close()
            
            # 3. 位移-时间图
            fig3 = plt.figure(figsize=(12, 8))
            plt.subplot(2, 2, 1)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    plt.plot(kinematics[marker_id]['time'], kinematics[marker_id]['displacement_x'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            plt.title('X方向位移')
            plt.xlabel('时间 (s)')
            plt.ylabel('X位移 (cm)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            plt.subplot(2, 2, 2)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    plt.plot(kinematics[marker_id]['time'], kinematics[marker_id]['displacement_y'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            plt.title('Y方向位移')
            plt.xlabel('时间 (s)')
            plt.ylabel('Y位移 (cm)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            plt.subplot(2, 2, 3)
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    plt.plot(kinematics[marker_id]['time'], kinematics[marker_id]['displacement_mag'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            plt.title('总位移')
            plt.xlabel('时间 (s)')
            plt.ylabel('位移大小 (cm)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            plt.subplot(2, 2, 4)
            for marker_id in self.tracking_confidences:
                if self.tracking_confidences[marker_id]:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    frames = list(range(len(self.tracking_confidences[marker_id])))
                    plt.plot(frames, self.tracking_confidences[marker_id], 
                            '-', color=color, alpha=0.6, label=f'标记 {marker_id+1}')
            plt.axhline(y=self.confidence_threshold, color='r', linestyle='--', alpha=0.5, label='置信度阈值')
            plt.title('跟踪置信度')
            plt.xlabel('帧')
            plt.ylabel('置信度')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.ylim(0, 1.1)
            
            plt.tight_layout()
            plt.savefig(os.path.join(result_dir, '03_位移分析.png'), dpi=300, bbox_inches='tight')
            plt.close()
            
            # 4. 速度-时间图
            fig4 = plt.figure(figsize=(10, 6))
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    plt.plot(kinematics[marker_id]['time'], kinematics[marker_id]['v_mag'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            plt.title('速度大小')
            plt.xlabel('时间 (s)')
            plt.ylabel('速度 (cm/s)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.savefig(os.path.join(result_dir, '04_速度分析.png'), dpi=300, bbox_inches='tight')
            plt.close()
            
            # 5. 加速度-时间图
            fig5 = plt.figure(figsize=(10, 6))
            for marker_id, data in cm_coords.items():
                if marker_id in kinematics:
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    plt.plot(kinematics[marker_id]['time'], kinematics[marker_id]['a_mag'], 
                            '-', color=color, label=f'标记 {marker_id+1}')
            plt.title('加速度大小')
            plt.xlabel('时间 (s)')
            plt.ylabel('加速度 (cm/s²)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.savefig(os.path.join(result_dir, '05_加速度分析.png'), dpi=300, bbox_inches='tight')
            plt.close()
            
            # 6. 阻尼分析图
            if self.damping_coefficients:
                fig6 = plt.figure(figsize=(12, 8))
                marker_count = len(self.damping_coefficients)
                rows = (marker_count + 1) // 2
                
                for idx, (marker_id, damping_data) in enumerate(self.damping_coefficients.items()):
                    if marker_id not in cm_coords:
                        continue
                    
                    ax = plt.subplot(rows, 2, idx+1)
                    time = np.array(cm_coords[marker_id]['frame']) / self.fps
                    y = np.array(cm_coords[marker_id]['y_cm'])
                    displacement = y - y[0]
                    
                    color = np.array(self.colors[marker_id % len(self.colors)]) / 255
                    ax.plot(time, displacement, '-', color=color, alpha=0.7, label='位移')
                    
                    for segment in damping_data:
                        start_frame = segment['start_frame']
                        end_frame = segment['end_frame']
                        damping_coeff = segment['damping_coefficient']
                        equilibrium_pos = segment['equilibrium_position']
                        r_squared = segment['r_squared']
                        
                        time_segment = time[start_frame:end_frame+1]
                        displacement_segment = displacement[start_frame:end_frame+1]
                        t_norm = time_segment - time_segment[0]
                        
                        A_guess = displacement_segment[0] - displacement_segment[-1] if displacement_segment[0] != displacement_segment[-1] else 1.0
                        try:
                            fit_curve = damping_model(t_norm, A_guess, damping_coeff, equilibrium_pos)
                            ax.plot(time_segment, fit_curve, '--', color=color, 
                                   label=f'阻尼拟合 (b={damping_coeff:.4f}, y0={equilibrium_pos:.2f}, R²={r_squared:.3f})')
                            ax.axvspan(time_segment[0], time_segment[-1], alpha=0.2, color=color)
                        except:
                            pass
                    
                    ax.set_xlabel('时间 (s)')
                    ax.set_ylabel('位移 (cm)')
                    ax.set_title(f'标记点 {marker_id+1} 阻尼分析')
                    ax.grid(True, alpha=0.3)
                    ax.legend(fontsize='small')
                
                plt.tight_layout()
                plt.savefig(os.path.join(result_dir, '06_阻尼分析.png'), dpi=300, bbox_inches='tight')
                plt.close()
            
            # 7. 统计信息图
            fig7 = plt.figure(figsize=(10, 8))
            plt.axis('off')
            
            stats_text = f'跟踪统计信息:\n\n'
            stats_text += f'视频文件: {os.path.basename(self.video_path)}\n'
            stats_text += f'总帧数: {self.frame_count}\n'
            stats_text += f'帧率: {self.fps:.1f} FPS\n'
            stats_text += f'时长: {self.frame_count/self.fps:.1f} s\n'
            stats_text += f'标度: 1像素 = {self.scale_factor:.4f} cm\n'
            stats_text += f'跟踪点数: {len(self.tracking_points)}\n'
            stats_text += f'跟踪算法: 光流法\n'
            stats_text += f'置信度阈值: {self.confidence_threshold}\n'
            
            for marker_id in range(len(self.tracking_points)):
                if marker_id in self.tracking_confidences and self.tracking_confidences[marker_id]:
                    confidences = self.tracking_confidences[marker_id]
                    avg_conf = np.mean(confidences)
                    low_conf_count = sum(1 for c in confidences if c < self.confidence_threshold)
                    low_conf_percent = (low_conf_count / len(confidences)) * 100
                    
                    stats_text += f'\n标记 {marker_id+1}:\n'
                    stats_text += f'  平均置信度: {avg_conf:.3f}\n'
                    stats_text += f'  低置信度: {low_conf_percent:.1f}%\n'
                    
                    if marker_id in self.damping_coefficients:
                        for segment in self.damping_coefficients[marker_id]:
                            stats_text += f'  阻尼系数: {segment["damping_coefficient"]:.4f}\n'
                            stats_text += f'  平衡位置: {segment["equilibrium_position"]:.4f}\n'
                            stats_text += f'  拟合优度: {segment["r_squared"]:.4f}\n'
            
            plt.text(0.1, 0.5, stats_text, fontsize=10, verticalalignment='center',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
            plt.savefig(os.path.join(result_dir, '07_统计信息.png'), dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"\n所有图像已保存到文件夹: {result_dir}")
            print("保存的图像包括:")
            print("  01_轨迹对比.png")
            print("  02_实际轨迹.png")
            print("  03_位移分析.png")
            print("  04_速度分析.png")
            print("  05_加速度分析.png")
            if self.damping_coefficients:
                print("  06_阻尼分析.png")
            print("  07_统计信息.png")
        
        except Exception as e:
            print(f"保存文件时出错: {e}")
            messagebox.showerror("错误", f"保存文件时出错: {e}")
    
    def settings_dialog(self):
        """设置对话框"""
        root = tk.Tk()
        root.title("跟踪设置")
        root.geometry("400x300")
        root.resizable(False, False)
        
        # 置信度阈值
        tk.Label(root, text="置信度阈值:", font=("Arial", 10)).grid(row=0, column=0, padx=10, pady=10, sticky='w')
        conf_var = tk.DoubleVar(value=self.confidence_threshold)
        conf_scale = tk.Scale(root, from_=0.1, to=1.0, resolution=0.05, 
                             orient=tk.HORIZONTAL, variable=conf_var, length=200)
        conf_scale.grid(row=0, column=1, padx=10, pady=10, sticky='ew')
        
        # 平滑窗口
        tk.Label(root, text="平滑窗口大小:", font=("Arial", 10)).grid(row=1, column=0, padx=10, pady=10, sticky='w')
        smooth_var = tk.IntVar(value=self.smoothing_window)
        smooth_scale = tk.Scale(root, from_=1, to=15, resolution=2, 
                               orient=tk.HORIZONTAL, variable=smooth_var, length=200)
        smooth_scale.grid(row=1, column=1, padx=10, pady=10, sticky='ew')
        
        def apply_settings():
            self.confidence_threshold = conf_var.get()
            self.smoothing_window = smooth_var.get()
            root.destroy()
            messagebox.showinfo("设置", "设置已保存")
        
        def cancel():
            root.destroy()
        
        tk.Button(root, text="应用", command=apply_settings, width=10, font=("Arial", 10)).grid(row=2, column=0, padx=10, pady=20)
        tk.Button(root, text="取消", command=cancel, width=10, font=("Arial", 10)).grid(row=2, column=1, padx=10, pady=20)
        
        root.mainloop()
    
    def cleanup(self):
        """清理资源"""
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()
    
    def run(self):
        """主运行函数"""
        print("="*60)
        print("光流法视频标志物跟踪分析系统 (修复版)")
        print("修复了重新标记模式鼠标点击无响应的问题")
        print("="*60)
        
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("欢迎", 
                "欢迎使用视频标志物跟踪分析系统！\n\n"
                "使用步骤:\n"
                "1. 加载视频文件\n"
                "2. 标定坐标系（选择两个点并输入实际距离）\n"
                "3. 选择要跟踪的标志物\n"
                "4. 开始自动跟踪\n"
                "5. 查看分析结果\n"
                "6. 保存数据\n\n"
                "重新标记功能(按R键):\n"
                "- 左键点击要修正的标记点\n"
                "- 左键点击新位置\n"
                "- 按A/D切换帧，按Enter确认\n"
                "- 按ESC取消重新标记"
            )
            
            while True:
                print("\n" + "-"*40)
                print("主菜单")
                print("-"*40)
                print("1. 加载视频")
                print("2. 标定坐标系")
                print("3. 选择标志物")
                print("4. 跟踪设置")
                print("5. 开始跟踪")
                print("6. 显示结果")
                print("7. 保存结果")
                print("8. 阻尼系数分析")
                print("9. 退出")
                
                try:
                    choice = input("\n请选择操作 (1-9): ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\n程序被用户中断")
                    break
                
                if choice == '1':
                    print("\n加载视频...")
                    if self.load_video():
                        print(f"成功加载视频")
                    else:
                        print("加载视频失败")
                
                elif choice == '2':
                    if self.video_path:
                        print("\n标定坐标系...")
                        if self.calibrate_coordinate_system():
                            print("坐标系标定成功")
                        else:
                            print("坐标系标定失败")
                    else:
                        print("请先加载视频")
                
                elif choice == '3':
                    if self.video_path:
                        print("\n选择标志物...")
                        if self.select_markers():
                            print(f"成功选择 {len(self.tracking_points)} 个标志物")
                        else:
                            print("选择标志物失败")
                    else:
                        print("请先加载视频")
                
                elif choice == '4':
                    print("\n跟踪设置...")
                    self.settings_dialog()
                
                elif choice == '5':
                    if self.video_path and self.tracking_points:
                        print("\n开始光流跟踪...")
                        print("跟踪过程中:")
                        print("  - 按ESC键: 停止跟踪")
                        print("  - 按P键: 暂停/继续")
                        print("  - 按R键: 重新标记模式")
                        print("重新标记模式:")
                        print("  - 左键点击标记点: 选择要重新标记的点")
                        print("  - 左键点击新位置: 设置新位置")
                        print("  - A/D键: 前一帧/后一帧")
                        print("  - Enter键: 确认并继续跟踪")
                        print("  - ESC键: 取消重新标记")
                        self.track_markers()
                    else:
                        print("请先加载视频并选择标志物")
                
                elif choice == '6':
                    if self.video_path and self.tracked_positions:
                        print("\n显示分析结果...")
                        self.plot_results()
                    else:
                        print("请先完成跟踪")
                
                elif choice == '7':
                    if self.video_path and self.tracked_positions:
                        print("\n保存结果...")
                        self.save_results()
                    else:
                        print("请先完成跟踪")
                
                elif choice == '8':
                    print("\n阻尼系数分析...")
                    self.analyze_damping()
                
                elif choice == '9':
                    print("\n感谢使用！")
                    break

                else:
                    print("无效选择，请重新输入")
        
        finally:
            self.cleanup()


def check_dependencies():
    """检查依赖库"""
    required_libraries = {
        'cv2': 'opencv-python',
        'numpy': 'numpy',
        'matplotlib': 'matplotlib',
        'pandas': 'pandas',
        'PIL': 'Pillow',
        'tkinter': 'python自带的tkinter',
        'scipy': 'scipy'
    }
    
    missing_libs = []
    for lib, pkg in required_libraries.items():
        try:
            if lib == 'cv2':
                __import__('cv2')
                print(f"OpenCV版本: {cv2.__version__}")
            elif lib == 'scipy':
                __import__('scipy')
                print(f"SciPy版本可用")
            else:
                __import__(lib)
        except ImportError:
            missing_libs.append(pkg)
    
    if missing_libs:
        print("缺少必要的库，请使用以下命令安装：")
        print(f"pip install {' '.join(missing_libs)}")
        return False
    
    return True


if __name__ == "__main__":
    # 检查依赖
    if not check_dependencies():
        exit(1)
    
    try:
        tracker = EnhancedVideoMarkerTracker()
        tracker.run()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        input("按Enter键退出...")