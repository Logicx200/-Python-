# 双摆模型仿真 - 混沌动力学可视化

## 🔄 项目概述
一个完整的双摆系统数值模拟程序，展示经典混沌系统的动力学行为。程序模拟多组初始条件略有不同的双摆，可视化它们在相空间和物理空间中的演化，生动展示"蝴蝶效应"。

## ✨ 核心特性
- **高精度数值积分**：使用SciPy的RK45方法（Dormand-Prince）
- **多系统并行模拟**：同时模拟100个初始条件微小的双摆
- **四维相空间可视化**：同时显示4个不同的相空间投影
- **混沌特性展示**：直观展示初始条件的敏感性
- **高质量动画输出**：支持MP4和GIF格式
- **科学级计算**：相对误差容限1e-8，确保数值精度

## 📦 安装要求
```bash
# 必需依赖
pip install numpy matplotlib scipy tqdm

# 可选：FFmpeg用于MP4输出（推荐）
# Windows: https://ffmpeg.org/download.html
# Ubuntu/Debian: sudo apt-get install ffmpeg
# macOS: brew install ffmpeg
```

## 🚀 快速开始
```bash
python 双摆.py
```

## 📐 物理模型

### 双摆系统定义
```
       θ₁
       │
       ● m₁
       │ L₁
       │
       ●───● m₂
       L₂  θ₂
```

### 运动方程（拉格朗日推导）
```python
# 系统动能
T = ½ m₁ v₁² + ½ m₂ v₂²

# 系统势能
V = m₁ g y₁ + m₂ g y₂

# 拉格朗日量
L = T - V

# 欧拉-拉格朗日方程
d/dt(∂L/∂θ̇ᵢ) - ∂L/∂θᵢ = 0
```

### 具体方程（代码实现）
```python
# 化简后的运动方程
θ1_dot = z1
θ2_dot = z2

z1_dot = (m2*L1*z1²*sin(Δ)*cos(Δ) + m2*g*sin(θ2)*cos(Δ) + 
          m2*L2*z2²*sin(Δ) - (m1+m2)*g*sin(θ1)) / 
         ((m1+m2)*L1 - m2*L1*cos²(Δ))

z2_dot = (-m2*L2*z2²*sin(Δ)*cos(Δ) + (m1+m2)*(g*sin(θ1)*cos(Δ) - 
          L1*z1²*sin(Δ) - g*sin(θ2))) / 
         ((L2/L1)*((m1+m2)*L1 - m2*L1*cos²(Δ)))
```

## ⚙️ 仿真参数

### 默认参数设置
```python
# 物理参数
L1, L2 = 1.0, 1.0      # 摆长 (m)
m1, m2 = 1.0, 1.0      # 质量 (kg)
g = 9.81               # 重力加速度 (m/s²)

# 初始条件
base_theta1 = np.pi / 2  # 90度
base_theta2 = np.pi / 2  # 90度

# 混沌参数
num_pendulums = 100      # 模拟的双摆数量
small_offset_range = 0.01  # 微小偏移范围 (±0.01弧度 ≈ ±0.57度)

# 时间参数
t_span = (0, 30)        # 模拟时间范围 (秒)
t_eval = np.linspace(0, 30, 1200)  # 输出时间点
```

### 参数影响分析
| 参数 | 对混沌的影响 | 对计算的影响 |
|------|--------------|--------------|
| 偏移范围 | 范围越大，发散越快 | 无显著影响 |
| 模拟时间 | 时间越长，差异越大 | 计算时间线性增加 |
| 摆长比 | 影响运动频率和模式 | 无显著影响 |
| 质量比 | 影响能量分配和耦合 | 无显著影响 |

## 🎨 可视化系统

### 5个子图布局
```
┌──────────────────┬──────────────────┐
│                  │                  │
│   物理空间       │   θ₁ vs ω₁       │
│   (双摆运动)     │   (相空间1)      │
│                  │                  │
├──────────────────┼──────────────────┤
│                  │                  │
│   θ₁ vs θ₂       │   ω₁ vs ω₂       │
│   (配置空间)     │   (速度空间)     │
│                  │                  │
└──────────────────┴──────────────────┘
│               θ₂ vs ω₂               │
│               (相空间2)              │
└──────────────────────────────────────┘
```

### 可视化元素说明
1. **物理空间**：实际的双摆运动轨迹
   - 摆杆：彩色连线
   - 轨迹：半透明尾迹
   - 质量点：彩色圆点

2. **相空间图**：动力系统状态空间
   - 当前状态：实心圆点
   - 历史轨迹：淡色曲线
   - 坐标范围：固定为[-π, π]和[-20, 20]

3. **颜色编码**：基于初始偏移大小
   - 颜色映射：plasma色彩图
   - 颜色深浅：表示初始偏移的大小
   - 偏移越大 → 颜色越亮（黄/白）
   - 偏移越小 → 颜色越暗（紫/蓝）

## 🔬 科学意义

### 混沌理论演示
```
初始条件：θ₁ = π/2 ± ε, θ₂ = π/2 ± ε
时间演化：t = 0 → 30秒
观察现象：微小初始差异 → 巨大长期差异
```

### 李雅普诺夫指数（概念性）
```python
# 混沌系统的特征：正的李雅普诺夫指数
# 表示相邻轨道的指数发散
λ ≈ (1/t) * ln(‖Δx(t)‖ / ‖Δx(0)‖)
# 对于双摆：λ > 0，表明混沌行为
```

### 相空间特性
1. **吸引子**：系统演化趋向的结构
2. **分形维数**：奇怪吸引子的复杂性度量
3. **庞加莱截面**：降维观察动力系统
4. **功率谱**：从时域到频域的变换

## 💻 代码结构

### 主要类和方法
```python
class DoublePendulum:
    def __init__(self, L1, L2, m1, m2, g)  # 初始化
    def equations(self, t, y)              # 运动方程
    def get_positions(self, theta1, theta2)  # 位置计算

# 主流程
1. 参数设置和初始化
2. 生成初始条件数组
3. 并行求解ODE（每个双摆）
4. 数据提取和预处理
5. 创建动画对象
6. 保存或显示动画
```

### 数值求解设置
```python
# 使用SciPy的solve_ivp
sol = solve_ivp(
    pendulum.equations,      # 微分方程
    t_span,                  # 时间区间
    y0,                      # 初始条件
    t_eval=t_eval,           # 输出时间点
    method='RK45',           # 龙格-库塔方法
    rtol=1e-8,               # 相对误差容限
    atol=1e-10               # 绝对误差容限
)
```

## 📊 性能优化

### 计算复杂度分析
```
时间复杂度：O(N × M × T)
其中：
N = 双摆数量 (默认100)
M = 每个时间步的计算量 (~100次浮点运算)
T = 时间步数量 (默认1200)

总计算量：100 × 100 × 1200 ≈ 1.2×10⁷ 次运算
预计时间：30-60秒（取决于CPU）
```

### 内存使用优化
```python
# 主要数据数组
theta1_list: 100 × 1200 = 120,000 个浮点数
theta2_list: 100 × 1200 = 120,000 个浮点数
omega1_list: 100 × 1200 = 120,000 个浮点数
omega2_list: 100 × 1200 = 120,000 个浮点数
x1_list, y1_list, x2_list, y2_list: 各 120,000 个浮点数

总内存：≈ 8 × 120,000 × 4字节 = 3.84 MB（float32）
```

### 并行计算优化
```python
# 可以使用multiprocessing并行求解
from multipiprocessing import Pool

def solve_single(args):
    pendulum, y0, t_span, t_eval = args
    return solve_ivp(pendulum.equations, t_span, y0, t_eval=t_eval)

with Pool(processes=4) as pool:
    solutions = pool.map(solve_single, arg_list)
```

## 🧪 实验设计

### 实验1：混沌敏感性研究
```python
# 研究不同偏移范围的影响
offset_ranges = [0.001, 0.005, 0.01, 0.02, 0.05]
# 观察：偏移越大，发散越快
```

### 实验2：能量守恒验证
```python
# 计算系统总能量
def total_energy(theta1, omega1, theta2, omega2):
    # 动能：T = ½ m₁ v₁² + ½ m₂ v₂²
    # 势能：V = m₁ g y₁ + m₂ g y₂
    return T + V

# 验证：理想情况下应守恒（实际有数值误差）
```

### 实验3：参数空间探索
```python
# 研究不同摆长比的影响
length_ratios = [0.5, 1.0, 2.0, 5.0]
# 观察：不同比例产生不同的运动模式
```

### 实验4：庞加莱截面
```python
# 在相空间中取截面
def poincare_section(theta2, omega2, threshold=0.0):
    # 当θ₁=0且dθ₁/dt>0时记录(θ₂, ω₂)
    # 产生分形图案
```

## 📈 结果分析

### 典型观察结果
1. **时间演化**：0-5秒：轨迹基本一致；5-15秒：开始发散；15-30秒：完全混乱
2. **相空间填充**：轨迹逐渐填满相空间区域
3. **颜色分布**：初始偏移大的轨迹发散更快
4. **能量变化**：总能量应基本守恒（验证数值精度）

### 定量分析指标
```python
# 1. 平均发散速度
def mean_divergence_rate(solutions):
    distances = []
    for i in range(len(solutions)):
        for j in range(i+1, len(solutions)):
            # 计算两个解之间的平均距离
            dist = np.mean(np.sqrt(
                (sol_i.theta1 - sol_j.theta1)**2 +
                (sol_i.theta2 - sol_j.theta2)**2
            ))
            distances.append(dist)
    return np.mean(distances)

# 2. 最大李雅普诺夫指数估计
def estimate_lyapunov(solutions, initial_distances):
    final_distances = []
    for i, sol_i in enumerate(solutions):
        for j, sol_j in enumerate(solutions):
            if i != j:
                # 计算最终距离
                final_dist = np.sqrt(
                    (sol_i.theta1[-1] - sol_j.theta1[-1])**2 +
                    (sol_i.theta2[-1] - sol_j.theta2[-1])**2
                )
                initial_dist = initial_distances[i][j]
                final_distances.append(final_dist / initial_dist)
    
    lambda_est = np.mean(np.log(final_distances)) / t_span[1]
    return lambda_est
```

## 🔧 高级配置

### 自定义动画设置
```python
# 修改动画参数
ani = FuncAnimation(
    fig, 
    animate, 
    frames=len(times),
    init_func=init, 
    blit=True,            # 使用blitting加速
    interval=20,          # 帧间隔(ms)，控制播放速度
    repeat=False,         # 不循环播放
    cache_frame_data=False  # 不缓存帧数据，节省内存
)
```

### 输出格式选择
```python
# MP4输出（需要FFmpeg）
ani.save('double_pendulum.mp4', 
         writer='ffmpeg', 
         fps=25,           # 帧率
         dpi=100,          # 分辨率
         bitrate=5000)     # 比特率(kbps)

# GIF输出（不需要外部依赖）
ani.save('double_pendulum.gif', 
         writer='pillow', 
         fps=20,           # GIF帧率较低
         dpi=80)           # 降低分辨率
```

### 性能调优参数
```python
# 降低精度要求，加速计算
rtol=1e-6      # 默认1e-8
atol=1e-8      # 默认1e-10

# 减少输出帧数
t_eval = np.linspace(0, 30, 600)  # 默认1200

# 减少模拟的双摆数量
num_pendulums = 50  # 默认100
```

## 🎓 教学应用

### 物理学概念演示
1. **经典力学**：拉格朗日力学、能量守恒
2. **非线性动力学**：混沌、敏感依赖性
3. **数值方法**：ODE求解、数值稳定性
4. **相空间概念**：状态空间、吸引子
5. **可视化技术**：科学可视化、动画制作

### 课堂实验设计
```python
# 实验报告模板
实验目标：观察双摆系统的混沌行为
实验步骤：
1. 运行默认参数的程序
2. 记录前5秒的运动（基本一致）
3. 记录15秒时的运动（开始发散）
4. 记录30秒时的运动（完全混乱）
5. 修改初始偏移，重复实验
6. 分析不同参数的影响
```

### 研究课题建议
1. **本科水平**：混沌系统的数值模拟和可视化
2. **研究生水平**：李雅普诺夫指数计算、分形维数估计
3. **研究课题**：双摆系统的参数空间分析、控制混沌

## 🔗 相关资源

### 经典参考文献
1. **教材**：
   - Strogatz, S. H. (2018). *Nonlinear Dynamics and Chaos*
   - Baker, G. L. (1996). *Chaos: An Introduction to Dynamical Systems*
   
2. **论文**：
   - Richter, P. H. (2019). *The Double Pendulum Fractal*
   - Shinbrot, T. (1993). *Chaos: Unpredictable Yet Controllable?*

3. **在线资源**：
   - [Double Pendulum on Wikipedia](https://en.wikipedia.org/wiki/Double_pendulum)
   - [Interactive Double Pendulum Simulator](http://www.myphysicslab.com/pendulum/double-pendulum-en.html)

### 类似仿真项目
1. **JavaScript版本**：p5.js双摆模拟
2. **MATLAB版本**：混沌工具箱
3. **Java版本**：Physics-based动画
4. **WebGL版本**：实时3D双摆

## 🚧 已知限制

### 数值误差来源
1. **截断误差**：ODE求解器的离散化误差
2. **舍入误差**：浮点数运算精度限制
3. **初始条件误差**：微小偏移的数值表示
4. **模型简化**：忽略空气阻力、摩擦等

### 可视化限制
1. **颜色重叠**：轨迹密集时颜色混合
2. **动态范围**：相空间范围固定可能不适用所有情况
3. **渲染性能**：大量轨迹点可能降低动画流畅度
4. **内存限制**：长时间模拟可能消耗大量内存

### 物理模型限制
1. **理想假设**：无阻尼、无驱动、刚性摆杆
2. **二维限制**：只能模拟平面内的运动
3. **小角度？**：实际上没有小角度近似，处理大角度运动
4. **能量守恒**：数值误差导致轻微能量漂移

## 🔮 扩展开发

### 计划功能
1. [ ] **3D可视化**：三维空间中的双摆运动
2. [ ] **交互式控制**：实时调整参数
3. [ ] **李雅普诺夫计算**：自动计算混沌指标
4. [ ] **庞加莱截面**：显示分形结构
5. [ ] **参数扫描**：自动探索参数空间
6. [ ] **教育模式**：分步讲解物理概念
7. [ ] **数据导出**：保存轨迹数据供分析

### 性能改进
1. [ ] **GPU加速**：使用JAX或CuPy加速计算
2. [ ] **实时渲染**：WebGL或Unity集成
3. [ ] **流式处理**：实时模拟和显示
4. [ ] **分布式计算**：多节点并行模拟

### 科学研究扩展
1. [ ] **分岔图**：显示系统随参数变化的行为
2. [ ] **功率谱分析**：频率域特性分析
3. [ ] **相空间重构**：从时间序列重建动力系统
4. [ ] **混沌控制**：演示混沌控制方法

## 📄 许可证

MIT License - 详见LICENSE文件

## 🤝 贡献指南

欢迎贡献：
1. **报告Bug**：提供复现步骤和系统信息
2. **功能请求**：描述应用场景和需求
3. **代码贡献**：遵循现有代码风格
4. **文档改进**：补充说明和示例
5. **测试案例**：提供新的实验设置

## 💬 社区支持

- **GitHub Issues**：问题讨论和功能请求
- **邮件列表**：开发讨论和公告
- **示例库**：分享有趣的双摆参数设置
- **教学资源**：分享课程材料和实验指导

---

**学术引用**：如果在研究中使用本代码，请引用：
```
@software{double_pendulum_sim,
  author = {Chenyu Wang},
  title = {Double Pendulum Chaos Simulation},
  year = {2025},
  url = {https://github.com/yourusername/double-pendulum}
}

> **教育用途**：本程序适合物理学、工程学、数学等专业的教学和实验演示。

