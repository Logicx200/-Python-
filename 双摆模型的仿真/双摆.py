import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from scipy.integrate import solve_ivp
import matplotlib.cm as cm
from tqdm import tqdm
import time
import os

class DoublePendulum:
    def __init__(self, L1=1.0, L2=1.0, m1=1.0, m2=1.0, g=9.81):
        self.L1, self.L2 = L1, L2
        self.m1, self.m2 = m1, m2
        self.g = g
        
    def equations(self, t, y):
        """Double pendulum equations of motion"""
        theta1, z1, theta2, z2 = y
        
        # Common terms
        delta = theta2 - theta1
        denom1 = (self.m1 + self.m2) * self.L1 - self.m2 * self.L1 * np.cos(delta) * np.cos(delta)
        denom2 = (self.L2 / self.L1) * denom1
        
        # Angular accelerations
        theta1_dot = z1
        theta2_dot = z2
        
        z1_dot = (self.m2 * self.L1 * z1 * z1 * np.sin(delta) * np.cos(delta) +
                  self.m2 * self.g * np.sin(theta2) * np.cos(delta) +
                  self.m2 * self.L2 * z2 * z2 * np.sin(delta) -
                  (self.m1 + self.m2) * self.g * np.sin(theta1)) / denom1
        
        z2_dot = (-self.m2 * self.L2 * z2 * z2 * np.sin(delta) * np.cos(delta) +
                  (self.m1 + self.m2) * (self.g * np.sin(theta1) * np.cos(delta) -
                  self.L1 * z1 * z1 * np.sin(delta) - self.g * np.sin(theta2))) / denom2
        
        return [theta1_dot, z1_dot, theta2_dot, z2_dot]
    
    def get_positions(self, theta1, theta2):
        """Calculate pendulum positions"""
        x1 = self.L1 * np.sin(theta1)
        y1 = -self.L1 * np.cos(theta1)  # Negative because y-axis points up
        x2 = x1 + self.L2 * np.sin(theta2)
        y2 = y1 - self.L2 * np.cos(theta2)
        return x1, y1, x2, y2

# Parameters
pendulum = DoublePendulum(L1=1.0, L2=1.0, m1=1.0, m2=1.0)

# 设置基准角度和微小偏移
base_theta1 = np.pi / 2  # 90度作为基准角度
base_theta2 = np.pi / 2  # 90度作为基准角度

# 微小偏移的范围（弧度）
small_offset_range = 0.01  # 约0.57度

# 创建100组在基准角度附近的微小偏移
num_pendulums = 100
initial_conditions = []
initial_values = []

print(f"Creating {num_pendulums} pendulums with small offsets around:")
print(f"Base θ₁ = {np.degrees(base_theta1):.1f}°, Base θ₂ = {np.degrees(base_theta2):.1f}°")
print(f"Offset range: ±{np.degrees(small_offset_range):.2f}°")

# 生成随机微小偏移
np.random.seed(42)  # 设置随机种子以便重现结果
for i in range(num_pendulums):
    # 在基准角度附近添加随机微小偏移
    theta1_offset = np.random.uniform(-small_offset_range, small_offset_range)
    theta2_offset = np.random.uniform(-small_offset_range, small_offset_range)
    
    theta1_init = base_theta1 + theta1_offset
    theta2_init = base_theta2 + theta2_offset
    
    initial_conditions.append([theta1_init, 0, theta2_init, 0])
    initial_values.append((theta1_init, theta2_init))

# 计算实际偏移统计
theta1_offsets = [val[0] - base_theta1 for val in initial_values]
theta2_offsets = [val[1] - base_theta2 for val in initial_values]

print(f"Actual offset statistics:")
print(f"θ₁ offsets: min={np.degrees(min(theta1_offsets)):.3f}°, max={np.degrees(max(theta1_offsets)):.3f}°, std={np.degrees(np.std(theta1_offsets)):.3f}°")
print(f"θ₂ offsets: min={np.degrees(min(theta2_offsets)):.3f}°, max={np.degrees(max(theta2_offsets)):.3f}°, std={np.degrees(np.std(theta2_offsets)):.3f}°")

# Time settings - 增加模拟时间以观察混沌行为
t_span = (0, 30)  # 30秒模拟
t_eval = np.linspace(0, 30, 1200)  # 1200帧

print(f"Solving double pendulum equations for {num_pendulums} initial conditions...")
solutions = []
for i, y0 in enumerate(tqdm(initial_conditions, desc="Solving ODEs")):
    sol = solve_ivp(pendulum.equations, t_span, y0, t_eval=t_eval, method='RK45', rtol=1e-8)
    solutions.append(sol)

theta1_list, omega1_list, theta2_list, omega2_list = [], [], [], []
x1_list, y1_list, x2_list, y2_list = [], [], [], []

for sol in tqdm(solutions, desc="Processing solutions"):
    theta1, omega1, theta2, omega2 = sol.y
    theta1_list.append(theta1)
    omega1_list.append(omega1)
    theta2_list.append(theta2)
    omega2_list.append(omega2)
    
    x1, y1, x2, y2 = pendulum.get_positions(theta1, theta2)
    x1_list.append(x1)
    y1_list.append(y1)
    x2_list.append(x2)
    y2_list.append(y2)

times = solutions[0].t

print("Creating small offsets animation...")

def create_small_offsets_animation():
    """创建微小偏移的动画"""
    plt.switch_backend('Agg')
    
    # 创建图形
    fig = plt.figure(figsize=(20, 10))
    
    # 定义固定的相图边界
    theta_limits = (-np.pi, np.pi)
    omega_limits = (-20, 20)
    
    # 计算轨迹的最大范围
    all_x2 = np.concatenate([x2 for x2 in x2_list])
    all_y2 = np.concatenate([y2 for y2 in y2_list])
    
    # 计算最大半径
    max_radius = max(np.sqrt(x**2 + y**2) for x, y in zip(all_x2, all_y2))
    display_range = max_radius * 1.3
    
    # 布局：左侧轨迹图占40%，右侧四幅相图占60%
    ax_physical = plt.subplot2grid((2, 10), (0, 0), rowspan=2, colspan=4)
    
    # 右侧四幅图
    ax_phase1 = plt.subplot2grid((2, 10), (0, 4), colspan=3)
    ax_phase2 = plt.subplot2grid((2, 10), (0, 7), colspan=3)
    ax_phase_theta = plt.subplot2grid((2, 10), (1, 4), colspan=3)
    ax_phase_omega = plt.subplot2grid((2, 10), (1, 7), colspan=3)
    
    # 设置物理空间
    ax_physical.set_xlim(-display_range, display_range)
    ax_physical.set_ylim(-display_range, display_range)
    ax_physical.set_aspect('equal')
    ax_physical.set_title('Double Pendulums - Small Offsets Chaos', fontsize=14)
    ax_physical.set_xlabel('x position')
    ax_physical.set_ylabel('y position')
    ax_physical.grid(True, alpha=0.3)
    
    # 绘制坐标轴参考线
    ax_physical.axhline(y=0, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    ax_physical.axvline(x=0, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    
    # 相图设置
    ax_phase1.set_xlim(theta_limits[0], theta_limits[1])
    ax_phase1.set_ylim(omega_limits[0], omega_limits[1])
    ax_phase1.set_title('Phase Space: θ₁ vs ω₁', fontsize=12)
    ax_phase1.set_xlabel('θ₁ (rad)')
    ax_phase1.set_ylabel('ω₁ (rad/s)')
    ax_phase1.grid(True, alpha=0.3)
    
    ax_phase2.set_xlim(theta_limits[0], theta_limits[1])
    ax_phase2.set_ylim(omega_limits[0], omega_limits[1])
    ax_phase2.set_title('Phase Space: θ₂ vs ω₂', fontsize=12)
    ax_phase2.set_xlabel('θ₂ (rad)')
    ax_phase2.set_ylabel('ω₂ (rad/s)')
    ax_phase2.grid(True, alpha=0.3)
    
    ax_phase_theta.set_xlim(theta_limits[0], theta_limits[1])
    ax_phase_theta.set_ylim(theta_limits[0], theta_limits[1])
    ax_phase_theta.set_title('Configuration Space: θ₁ vs θ₂', fontsize=12)
    ax_phase_theta.set_xlabel('θ₁ (rad)')
    ax_phase_theta.set_ylabel('θ₂ (rad)')
    ax_phase_theta.grid(True, alpha=0.3)
    
    ax_phase_omega.set_xlim(omega_limits[0], omega_limits[1])
    ax_phase_omega.set_ylim(omega_limits[0], omega_limits[1])
    ax_phase_omega.set_title('Velocity Space: ω₁ vs ω₂', fontsize=12)
    ax_phase_omega.set_xlabel('ω₁ (rad/s)')
    ax_phase_omega.set_ylabel('ω₂ (rad/s)')
    ax_phase_omega.grid(True, alpha=0.3)
    
    # 创建颜色映射 - 使用热图表示偏移大小
    offset_magnitudes = [np.sqrt((theta1 - base_theta1)**2 + (theta2 - base_theta2)**2) 
                        for theta1, theta2 in initial_values]
    colors = cm.plasma(np.array(offset_magnitudes) / max(offset_magnitudes))
    
    # 初始化所有图形元素
    pendulum_lines = []
    pendulum_trajectories = []
    pendulum_markers = []
    
    phase1_points = []
    phase1_trajectories = []
    phase2_points = []
    phase2_trajectories = []
    phase_theta_points = []
    phase_theta_trajectories = []
    phase_omega_points = []
    phase_omega_trajectories = []
    
    for idx in range(len(initial_conditions)):
        color = colors[idx]
        
        # 物理空间
        line, = ax_physical.plot([], [], 'o-', lw=0.7, markersize=1.2, 
                                color=color, alpha=0.7)
        trajectory, = ax_physical.plot([], [], '-', lw=0.5, 
                                      color=color, alpha=0.3)
        marker, = ax_physical.plot([], [], 'o', markersize=1.5, 
                                  color=color, alpha=0.8)
        
        pendulum_lines.append(line)
        pendulum_trajectories.append(trajectory)
        pendulum_markers.append(marker)
        
        # 相图元素
        phase1_point, = ax_phase1.plot([], [], 'o', markersize=1.5, 
                                      color=color, alpha=0.8)
        phase1_traj, = ax_phase1.plot([], [], '-', lw=0.4, 
                                     color=color, alpha=0.2)
        phase1_points.append(phase1_point)
        phase1_trajectories.append(phase1_traj)
        
        phase2_point, = ax_phase2.plot([], [], 'o', markersize=1.5, 
                                      color=color, alpha=0.8)
        phase2_traj, = ax_phase2.plot([], [], '-', lw=0.4, 
                                     color=color, alpha=0.2)
        phase2_points.append(phase2_point)
        phase2_trajectories.append(phase2_traj)
        
        phase_theta_point, = ax_phase_theta.plot([], [], 'o', markersize=1.5, 
                                               color=color, alpha=0.8)
        phase_theta_traj, = ax_phase_theta.plot([], [], '-', lw=0.4, 
                                              color=color, alpha=0.2)
        phase_theta_points.append(phase_theta_point)
        phase_theta_trajectories.append(phase_theta_traj)
        
        phase_omega_point, = ax_phase_omega.plot([], [], 'o', markersize=1.5, 
                                               color=color, alpha=0.8)
        phase_omega_traj, = ax_phase_omega.plot([], [], '-', lw=0.4, 
                                              color=color, alpha=0.2)
        phase_omega_points.append(phase_omega_point)
        phase_omega_trajectories.append(phase_omega_traj)
    
    # 存储轨迹数据
    traj_x_list = [[] for _ in range(len(initial_conditions))]
    traj_y_list = [[] for _ in range(len(initial_conditions))]
    
    phase1_x_list = [[] for _ in range(len(initial_conditions))]
    phase1_y_list = [[] for _ in range(len(initial_conditions))]
    
    phase2_x_list = [[] for _ in range(len(initial_conditions))]
    phase2_y_list = [[] for _ in range(len(initial_conditions))]
    
    phase_theta_x_list = [[] for _ in range(len(initial_conditions))]
    phase_theta_y_list = [[] for _ in range(len(initial_conditions))]
    
    phase_omega_x_list = [[] for _ in range(len(initial_conditions))]
    phase_omega_y_list = [[] for _ in range(len(initial_conditions))]
    
    # 添加图例说明
    ax_physical.text(0.02, 0.98, 
                    f'Total: {len(initial_conditions)} pendulums\n'
                    f'Base θ₁ = {np.degrees(base_theta1):.1f}°\n'
                    f'Base θ₂ = {np.degrees(base_theta2):.1f}°\n'
                    f'Offset range: ±{np.degrees(small_offset_range):.2f}°\n'
                    f'Color: offset magnitude',
                    transform=ax_physical.transAxes, fontsize=8,
                    verticalalignment='top', 
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout(pad=3.0)

    def init():
        all_artists = []
        
        for i in range(len(initial_conditions)):
            pendulum_lines[i].set_data([], [])
            pendulum_trajectories[i].set_data([], [])
            pendulum_markers[i].set_data([], [])
            
            phase1_points[i].set_data([], [])
            phase1_trajectories[i].set_data([], [])
            phase2_points[i].set_data([], [])
            phase2_trajectories[i].set_data([], [])
            
            phase_theta_points[i].set_data([], [])
            phase_theta_trajectories[i].set_data([], [])
            phase_omega_points[i].set_data([], [])
            phase_omega_trajectories[i].set_data([], [])
        
        all_artists.extend(pendulum_lines)
        all_artists.extend(pendulum_trajectories)
        all_artists.extend(pendulum_markers)
        all_artists.extend(phase1_points)
        all_artists.extend(phase1_trajectories)
        all_artists.extend(phase2_points)
        all_artists.extend(phase2_trajectories)
        all_artists.extend(phase_theta_points)
        all_artists.extend(phase_theta_trajectories)
        all_artists.extend(phase_omega_points)
        all_artists.extend(phase_omega_trajectories)
        
        return all_artists

    def animate(frame):
        current_frame = frame
        
        for idx in range(len(initial_conditions)):
            # 物理空间更新
            current_x = [0, x1_list[idx][current_frame], x2_list[idx][current_frame]]
            current_y = [0, y1_list[idx][current_frame], y2_list[idx][current_frame]]
            pendulum_lines[idx].set_data(current_x, current_y)
            
            # 更新轨迹
            traj_x_list[idx].append(x2_list[idx][current_frame])
            traj_y_list[idx].append(y2_list[idx][current_frame])
            
            pendulum_trajectories[idx].set_data(traj_x_list[idx], traj_y_list[idx])
            pendulum_markers[idx].set_data([x2_list[idx][current_frame]], 
                                         [y2_list[idx][current_frame]])
            
            # 更新相图
            current_theta1 = theta1_list[idx][current_frame]
            current_omega1 = omega1_list[idx][current_frame]
            current_theta2 = theta2_list[idx][current_frame]
            current_omega2 = omega2_list[idx][current_frame]
            
            phase1_points[idx].set_data([current_theta1], [current_omega1])
            phase1_x_list[idx].append(current_theta1)
            phase1_y_list[idx].append(current_omega1)
            phase1_trajectories[idx].set_data(phase1_x_list[idx], phase1_y_list[idx])
            
            phase2_points[idx].set_data([current_theta2], [current_omega2])
            phase2_x_list[idx].append(current_theta2)
            phase2_y_list[idx].append(current_omega2)
            phase2_trajectories[idx].set_data(phase2_x_list[idx], phase2_y_list[idx])
            
            phase_theta_points[idx].set_data([current_theta1], [current_theta2])
            phase_theta_x_list[idx].append(current_theta1)
            phase_theta_y_list[idx].append(current_theta2)
            phase_theta_trajectories[idx].set_data(phase_theta_x_list[idx], phase_theta_y_list[idx])
            
            phase_omega_points[idx].set_data([current_omega1], [current_omega2])
            phase_omega_x_list[idx].append(current_omega1)
            phase_omega_y_list[idx].append(current_omega2)
            phase_omega_trajectories[idx].set_data(phase_omega_x_list[idx], phase_omega_y_list[idx])
        
        # 更新标题
        ax_physical.set_title(f'Double Pendulums - Small Offsets Chaos (t = {times[current_frame]:.1f}s)', fontsize=14)
        
        all_artists = []
        all_artists.extend(pendulum_lines)
        all_artists.extend(pendulum_trajectories)
        all_artists.extend(pendulum_markers)
        all_artists.extend(phase1_points)
        all_artists.extend(phase1_trajectories)
        all_artists.extend(phase2_points)
        all_artists.extend(phase2_trajectories)
        all_artists.extend(phase_theta_points)
        all_artists.extend(phase_theta_trajectories)
        all_artists.extend(phase_omega_points)
        all_artists.extend(phase_omega_trajectories)
        
        return all_artists

    print("Creating small offsets animation object...")
    ani = FuncAnimation(fig, animate, frames=len(times),
                        init_func=init, blit=True, interval=20, repeat=False, cache_frame_data=False)
    
    return ani, fig

# 其余函数保持不变...
def check_ffmpeg():
    from matplotlib.animation import writers
    return 'ffmpeg' in writers.list()

def save_animation_gif(ani, filename, total_frames, fps=25):
    print(f"Saving as GIF ({total_frames} frames, fps={fps})...")
    start_time = time.time()
    
    def progress_callback(current, total):
        if current % 20 == 0 or current == total - 1:
            progress = (current + 1) / total * 100
            print(f"Progress: {progress:.1f}% ({current + 1}/{total} frames)")
    
    try:
        ani.save(filename, writer='pillow', fps=fps, 
                progress_callback=progress_callback)
        end_time = time.time()
        print(f"Animation saved successfully in {end_time - start_time:.2f} seconds!")
        print(f"File saved as: {os.path.abspath(filename)}")
        return True
    except Exception as e:
        print(f"Error saving GIF: {e}")
        return False

def save_animation_mp4(ani, filename, total_frames, fps=25, dpi=100):
    print(f"Attempting to save as MP4 ({total_frames} frames, fps={fps})...")
    start_time = time.time()
    
    def progress_callback(current, total):
        if current % 20 == 0 or current == total - 1:
            progress = (current + 1) / total * 100
            print(f"Progress: {progress:.1f}% ({current + 1}/{total} frames)")
    
    try:
        ani.save(filename, writer='ffmpeg', fps=fps, dpi=dpi,
                progress_callback=progress_callback)
        end_time = time.time()
        print(f"MP4 saved successfully in {end_time - start_time:.2f} seconds!")
        print(f"File saved as: {os.path.abspath(filename)}")
        return True
    except Exception as e:
        print(f"Error saving MP4: {e}")
        return False

if __name__ == "__main__":
    print("Checking available animation writers...")
    from matplotlib.animation import writers
    available_writers = writers.list()
    print(f"Available writers: {available_writers}")
    
    ani, fig = create_small_offsets_animation()
    
    success = False
    
    if 'ffmpeg' in available_writers:
        print("FFmpeg is available, attempting to save as MP4...")
        success = save_animation_mp4(ani, 'double_pendulum_small_offsets.mp4', 
                                   total_frames=len(times), fps=25, dpi=100)
    
    if not success:
        print("FFmpeg not available or failed, saving as GIF instead...")
        success = save_animation_gif(ani, 'double_pendulum_small_offsets.gif', 
                                   total_frames=len(times), fps=20)
    
    if not success:
        print("\n" + "="*50)
        print("SAVE FAILED - SOLUTIONS:")
        print("1. Install FFmpeg for MP4 support:")
        print("   - Windows: Download from https://ffmpeg.org/")
        print("   - Add ffmpeg to your PATH")
        print("2. Or reduce animation complexity:")
        print("   - Decrease number of pendulums")
        print("   - Decrease number of frames")
        print("="*50)
    
    plt.close(fig)
    print("Small offsets animation process completed!")