#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spring-magnet-coil (vertical sleeve) with electromagnetic damping.
ODE:
  y' = v
  v' = (-k*y + N*i*dphi_dz(y))/m
  i' = ( -R_total*i - N*dphi_dz(y)*v )/L
where R_total = R_coil + R_ext.

Outputs:
- Static PNGs: y-t, v-t, i-t (multi-case, with zoom), energy, phase, EM coupling.
- Animation: left scene + right 2x3 live plots (y, v, i, energy, phase, EM).
  Saves MP4 (if ffmpeg), and GIF (Pillow). GIF 包含右侧所有图。
- GUI panel (Tkinter) to edit parameters and run simulations.
"""

import argparse
import threading
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.animation as animation
import sys
import io
import time
import os

# 尝试导入性能优化库
try:
    from numba import jit
    USE_NUMBA = True
except ImportError:
    USE_NUMBA = False
    print("提示: 安装numba可以进一步提高性能: pip install numba")

try:
    from scipy.integrate import solve_ivp
    USE_SCIPY = True
except ImportError:
    USE_SCIPY = False

# ---------- 性能优化函数 ----------
if USE_NUMBA:
    @jit(nopython=True)
    def dphi_dz_one_turn(z, mu0, m_dipole, a):
        num = -3.0 * mu0 * m_dipole * a * a * z
        den = 2.0 * (a * a + z * z) ** 2.5
        return num / den
    
    @jit(nopython=True)
    def f_state_numba(t, y, m, k, N_turns, L_coil, z_coil, mu0, m_dipole, a, R_total):
        pos, vel, cur = y
        dphidz = dphi_dz_one_turn(pos - z_coil, mu0, m_dipole, a)
        dy_dt = vel
        dv_dt = (-k * pos + N_turns * cur * dphidz) / m
        di_dt = (-R_total * cur - N_turns * dphidz * vel) / L_coil
        return np.array([dy_dt, dv_dt, di_dt])
else:
    def dphi_dz_one_turn(z, mu0, m_dipole, a):
        num = -3.0 * mu0 * m_dipole * a * a * z
        den = 2.0 * (a * a + z * z) ** 2.5
        return num / den

# 缓存dphi_dz计算
class CachedDPhiDZ:
    def __init__(self, mu0, m_dipole, a, cache_size=10000):
        self.mu0 = mu0
        self.m_dipole = m_dipole
        self.a = a
        self.cache = {}
        self.cache_size = cache_size
        
    def __call__(self, z):
        z_key = round(z, 8)  # 四舍五入增加缓存命中率
        if z_key in self.cache:
            return self.cache[z_key]
        
        # 计算新值
        num = -3.0 * self.mu0 * self.m_dipole * self.a * self.a * z
        den = 2.0 * (self.a * self.a + z * z) ** 2.5
        result = num / den
        
        # 管理缓存大小
        if len(self.cache) >= self.cache_size:
            self.cache.pop(next(iter(self.cache)))
        self.cache[z_key] = result
        return result

# ---------- Optional progress bar (tqdm with fallback) ----------
def _build_progress():
    try:
        from tqdm import tqdm as _tqdm  # type: ignore
        class TqdmWrapper:
            def __init__(self, total, desc, ui_cb=None, stop_event=None):
                self._bar = _tqdm(total=total, desc=desc, unit="step")
                self._last = 0
                self._ui_cb = ui_cb
                self._desc = desc
                self._stop_event = stop_event
            def update_to(self, i):
                if self._stop_event and self._stop_event.is_set():
                    raise StopIteration("Simulation stopped by user")
                delta = int(i) - self._last
                if delta > 0:
                    self._bar.update(delta)
                    self._last += delta
                    if self._ui_cb:
                        self._ui_cb(self._desc, self._last / max(1, self._bar.total))
            def update(self, n=1):
                self.update_to(self._last + n)
            def close(self):
                self._bar.close()
                if self._ui_cb:
                    self._ui_cb(self._desc, 1.0)
        return TqdmWrapper
    except Exception:
        class SimpleBar:
            def __init__(self, total, desc, ui_cb=None, stop_event=None):
                self.total = max(int(total), 1)
                self.count = 0
                self.desc = desc
                self._last_pct = -1
                self._ui_cb = ui_cb
                self._stop_event = stop_event
                print(f"{self.desc}: 0% ", end="", flush=True)
            def update_to(self, i):
                if self._stop_event and self._stop_event.is_set():
                    raise StopIteration("Simulation stopped by user")
                self.count = int(i)
                pct = int(100 * self.count / self.total)
                if pct != self._last_pct and (pct % 5 == 0 or self.count >= self.total):
                    print("\r" + f"{self.desc}: {pct:3d}% ", end="", flush=True)
                    self._last_pct = pct
                if self._ui_cb:
                    self._ui_cb(self.desc, min(1.0, self.count / self.total))
            def update(self, n=1):
                self.update_to(self.count + n)
            def close(self):
                print()
                if self._ui_cb:
                    self._ui_cb(self.desc, 1.0)
        return SimpleBar

ProgressBar = _build_progress()

# ---------- Core simulation (parameterized) ----------
def f_state(t, y, p, R_total):
    pos, vel, cur = y
    dphidz = p["dphi_dz_func"](pos - p["z_coil"])
    dy_dt = vel
    dv_dt = (-p["k"] * pos + p["N_turns"] * cur * dphidz) / p["m"]
    di_dt = (-R_total * cur - p["N_turns"] * dphidz * vel) / p["L_coil"]
    return np.array([dy_dt, dv_dt, di_dt])

def rk4_step(fun, t, y, h, *args):
    k1 = fun(t, y, *args)
    k2 = fun(t + 0.5*h, y + 0.5*h*k1, *args)
    k3 = fun(t + 0.5*h, y + 0.5*h*k2, *args)
    k4 = fun(t + h,     y + h*k3, *args)
    return y + (h/6.0)*(k1 + 2*k2 + 2*k3 + k4)

def choose_dt(params, Rext_cases):
    m, k = params["m"], params["k"]
    L = params["L_coil"]
    R_coil = params["R_coil"]
    w_mech = np.sqrt(k / m)
    T_mech = 2.0 * np.pi / max(w_mech, 1e-12)
    tau_list = []
    for Rext in Rext_cases:
        Rtot = R_coil + Rext
        if np.isfinite(Rtot) and Rtot > 0:
            tau_list.append(L / Rtot)
    tau_min = min(tau_list) if tau_list else T_mech
    # Heuristics (explicit RK4): tau/20 and period/2000; hard cap from params
    dt_mech = T_mech / max(50.0, params.get("mech_steps_per_period", 2000))
    dt_elec = tau_min / max(5.0, params.get("elec_divisor", 20))
    dt_cap = params.get("dt_cap", 5.0e-5)
    dt = min(dt_mech, dt_elec, dt_cap)
    return dt, T_mech, tau_min

def integrate_case(params, Rext, t, dt, desc=None, ui_cb=None, stop_event=None):
    R_total = params["R_coil"] + Rext
    
    # 使用更高效的状态更新方法
    if USE_NUMBA and not params.get("fast_mode", False):
        # 使用numba加速的版本
        return integrate_case_numba(params, Rext, t, dt, desc, ui_cb, stop_event)
    elif USE_SCIPY and params.get("use_scipy", False):
        # 使用scipy的ODE求解器
        return integrate_case_scipy(params, Rext, t, desc, ui_cb, stop_event)
    else:
        # 原始RK4方法
        return integrate_case_rk4(params, Rext, t, dt, desc, ui_cb, stop_event)

def integrate_case_rk4(params, Rext, t, dt, desc=None, ui_cb=None, stop_event=None):
    R_total = params["R_coil"] + Rext
    y = np.zeros_like(t); v = np.zeros_like(t); i = np.zeros_like(t)
    e_heat_tot = np.zeros_like(t)
    e_heat_coil = np.zeros_like(t)
    e_heat_load = np.zeros_like(t)

    state = np.array([params["y0"], params["v0"], 0.0], dtype=float)
    y[0], v[0], i[0] = state
    p_prev_tot  = (i[0]*i[0]*R_total)
    p_prev_coil = (i[0]*i[0]*params["R_coil"])
    p_prev_load = (i[0]*i[0]*Rext)

    total = t.size - 1
    bar = ProgressBar(total=total, desc=(desc or "Integrating"), ui_cb=ui_cb, stop_event=stop_event)
    for n in range(total):
        if stop_event and stop_event.is_set():
            break
        tn = t[n]
        state = rk4_step(f_state, tn, state, dt, params, R_total)
        y[n+1], v[n+1], i[n+1] = state
        p_now_tot  = (i[n+1]*i[n+1]*R_total)
        p_now_coil = (i[n+1]*i[n+1]*params["R_coil"])
        p_now_load = (i[n+1]*i[n+1]*Rext)
        e_heat_tot[n+1]  = e_heat_tot[n]  + 0.5*(p_prev_tot  + p_now_tot )*dt
        e_heat_coil[n+1] = e_heat_coil[n] + 0.5*(p_prev_coil + p_now_coil)*dt
        e_heat_load[n+1] = e_heat_load[n] + 0.5*(p_prev_load + p_now_load)*dt
        p_prev_tot, p_prev_coil, p_prev_load = p_now_tot, p_now_coil, p_now_load
        bar.update(1)
    bar.close()

    e_kin = 0.5 * params["m"] * v * v
    e_spring = 0.5 * params["k"] * y * y
    e_L = 0.5 * params["L_coil"] * i * i
    e_mech = e_kin + e_spring
    e_total = e_mech + e_L + e_heat_tot
    return {
        "Rext": Rext, "R_total": R_total,
        "y": y, "v": v, "i": i,
        "E_kin": e_kin, "E_spring": e_spring, "E_L": e_L,
        "E_mech": e_mech, "E_heat_total": e_heat_tot,
        "E_heat_coil": e_heat_coil, "E_heat_load": e_heat_load,
        "E_total": e_total,
    }

def integrate_case_numba(params, Rext, t, dt, desc=None, ui_cb=None, stop_event=None):
    """使用numba加速的积分方法"""
    R_total = params["R_coil"] + Rext
    y = np.zeros_like(t); v = np.zeros_like(t); i = np.zeros_like(t)
    e_heat_tot = np.zeros_like(t)
    e_heat_coil = np.zeros_like(t)
    e_heat_load = np.zeros_like(t)

    state = np.array([params["y0"], params["v0"], 0.0], dtype=float)
    y[0], v[0], i[0] = state
    p_prev_tot  = (i[0]*i[0]*R_total)
    p_prev_coil = (i[0]*i[0]*params["R_coil"])
    p_prev_load = (i[0]*i[0]*Rext)

    total = t.size - 1
    bar = ProgressBar(total=total, desc=(desc or "Integrating (Numba)"), ui_cb=ui_cb, stop_event=stop_event)
    
    # 提取参数用于numba函数
    m = params["m"]
    k = params["k"]
    N_turns = params["N_turns"]
    L_coil = params["L_coil"]
    z_coil = params["z_coil"]
    mu0 = params["mu0"]
    m_dipole = params["m_dipole"]
    a = params["a"]
    
    for n in range(total):
        if stop_event and stop_event.is_set():
            break
        tn = t[n]
        # 使用numba加速的RK4步骤
        state = rk4_step_numba(tn, state, dt, m, k, N_turns, L_coil, z_coil, mu0, m_dipole, a, R_total)
        y[n+1], v[n+1], i[n+1] = state
        p_now_tot  = (i[n+1]*i[n+1]*R_total)
        p_now_coil = (i[n+1]*i[n+1]*params["R_coil"])
        p_now_load = (i[n+1]*i[n+1]*Rext)
        e_heat_tot[n+1]  = e_heat_tot[n]  + 0.5*(p_prev_tot  + p_now_tot )*dt
        e_heat_coil[n+1] = e_heat_coil[n] + 0.5*(p_prev_coil + p_now_coil)*dt
        e_heat_load[n+1] = e_heat_load[n] + 0.5*(p_prev_load + p_now_load)*dt
        p_prev_tot, p_prev_coil, p_prev_load = p_now_tot, p_now_coil, p_now_load
        bar.update(1)
    bar.close()

    e_kin = 0.5 * params["m"] * v * v
    e_spring = 0.5 * params["k"] * y * y
    e_L = 0.5 * params["L_coil"] * i * i
    e_mech = e_kin + e_spring
    e_total = e_mech + e_L + e_heat_tot
    return {
        "Rext": Rext, "R_total": R_total,
        "y": y, "v": v, "i": i,
        "E_kin": e_kin, "E_spring": e_spring, "E_L": e_L,
        "E_mech": e_mech, "E_heat_total": e_heat_tot,
        "E_heat_coil": e_heat_coil, "E_heat_load": e_heat_load,
        "E_total": e_total,
    }

def rk4_step_numba(t, y, h, m, k, N_turns, L_coil, z_coil, mu0, m_dipole, a, R_total):
    """使用numba加速的RK4步骤"""
    k1 = f_state_numba(t, y, m, k, N_turns, L_coil, z_coil, mu0, m_dipole, a, R_total)
    k2 = f_state_numba(t + 0.5*h, y + 0.5*h*k1, m, k, N_turns, L_coil, z_coil, mu0, m_dipole, a, R_total)
    k3 = f_state_numba(t + 0.5*h, y + 0.5*h*k2, m, k, N_turns, L_coil, z_coil, mu0, m_dipole, a, R_total)
    k4 = f_state_numba(t + h,     y + h*k3, m, k, N_turns, L_coil, z_coil, mu0, m_dipole, a, R_total)
    return y + (h/6.0)*(k1 + 2*k2 + 2*k3 + k4)

def integrate_case_scipy(params, Rext, t, desc=None, ui_cb=None, stop_event=None):
    """使用scipy的ODE求解器"""
    R_total = params["R_coil"] + Rext
    
    # 定义ODE系统
    def ode_system(t, y):
        return f_state(t, y, params, R_total)
    
    # 初始条件
    y0 = [params["y0"], params["v0"], 0.0]
    
    # 使用RK45方法求解
    print(f"使用Scipy ODE求解器...")
    sol = solve_ivp(ode_system, [t[0], t[-1]], y0, t_eval=t, method='RK45', rtol=1e-6, atol=1e-9)
    
    y = sol.y[0]
    v = sol.y[1]
    i = sol.y[2]
    
    # 计算能量
    e_kin = 0.5 * params["m"] * v * v
    e_spring = 0.5 * params["k"] * y * y
    e_L = 0.5 * params["L_coil"] * i * i
    
    # 计算热量（需要积分功率）
    p_heat_total = i*i*R_total
    e_heat_tot = np.zeros_like(t)
    for n in range(1, len(t)):
        e_heat_tot[n] = np.trapz(p_heat_total[:n+1], t[:n+1])
    
    e_mech = e_kin + e_spring
    e_total = e_mech + e_L + e_heat_tot
    
    return {
        "Rext": Rext, "R_total": R_total,
        "y": y, "v": v, "i": i,
        "E_kin": e_kin, "E_spring": e_spring, "E_L": e_L,
        "E_mech": e_mech, "E_heat_total": e_heat_tot,
        "E_heat_coil": np.zeros_like(t),  # 简化计算
        "E_heat_load": np.zeros_like(t),  # 简化计算
        "E_total": e_total,
    }

def integrate_open(params, t, dt, desc=None, ui_cb=None, stop_event=None):
    # i=0, pure mass-spring
    y = np.zeros_like(t); v = np.zeros_like(t); i = np.zeros_like(t)
    s = np.array([params["y0"], params["v0"]], dtype=float)
    def f_mech(t, s):
        pos, vel = s
        return np.array([vel, -params["k"] * pos / params["m"]])
    def rk4_mech(t, s, h):
        k1 = f_mech(t, s)
        k2 = f_mech(t+0.5*h, s+0.5*h*k1)
        k3 = f_mech(t+0.5*h, s+0.5*h*k2)
        k4 = f_mech(t+h,     s+h*k3)
        return s + (h/6.0)*(k1 + 2*k2 + 2*k3 + k4)
    total = t.size - 1
    bar = ProgressBar(total=total, desc=(desc or "Integrating open (i=0)"), ui_cb=ui_cb, stop_event=stop_event)
    y[0], v[0] = s
    for n in range(total):
        if stop_event and stop_event.is_set():
            break
        s = rk4_mech(t[n], s, dt)
        y[n+1], v[n+1] = s
        bar.update(1)
    bar.close()
    e_kin = 0.5 * params["m"] * v * v
    e_spring = 0.5 * params["k"] * y * y
    zeros = np.zeros_like(t)
    e_mech = e_kin + e_spring
    return {
        "Rext": np.inf, "R_total": np.inf,
        "y": y, "v": v, "i": i,
        "E_kin": e_kin, "E_spring": e_spring, "E_L": zeros,
        "E_mech": e_mech, "E_heat_total": zeros,
        "E_heat_coil": zeros, "E_heat_load": zeros,
        "E_total": e_mech.copy(),
    }

# ---------- Static plots ----------
def save_zoom_plot(x, ys, labels, xlabel, ylabel, title, out_all, out_zoom, t_zoom=0.3):
    plt.figure(figsize=(10, 5))
    for y, lb in zip(ys, labels):
        plt.plot(x, y, label=lb)
    plt.xlabel(xlabel); plt.ylabel(ylabel); plt.title(title)
    plt.grid(True, alpha=0.35); plt.legend(); plt.tight_layout()
    plt.savefig(out_all, dpi=140)

    mask = x <= t_zoom
    plt.figure(figsize=(10, 4))
    for y, lb in zip(ys, labels):
        plt.plot(x[mask], y[mask], label=lb)
    plt.xlabel(xlabel); plt.ylabel(ylabel); plt.title(title + " (zoom)")
    plt.grid(True, alpha=0.35); plt.legend(); plt.tight_layout()
    plt.savefig(out_zoom, dpi=140)

# ---------- Spring polyline for scene ----------
def spring_polyline(y_top, y_bottom, x_center=0.0, width=0.04, n_zigs=12):
    ys = np.linspace(y_top, y_bottom, 2*n_zigs + 1)
    xs = np.empty_like(ys)
    xs[0] = x_center
    for k in range(1, len(ys)-1):
        xs[k] = x_center + (width/2 if k % 2 else -width/2)
    xs[-1] = x_center
    return xs, ys

# ---------- Animation (scene + 2x3 live plots) ----------
def render_animation(params, t, case, case_label, fps, out_base, ui_cb=None, stop_event=None):
    # 快速模式设置
    if params.get("fast_mode", False):
        fps = min(fps, 20)  # 限制帧率
        # 减少帧数
        duration = t[-1] - t[0]
        max_frames = min(int(duration * fps), 150)
        idx = np.linspace(0, len(t)-1, max_frames, dtype=int)
    else:
        duration = t[-1] - t[0]
        n_frames = int(max(2, round(duration * fps)))
        idx = np.linspace(0, len(t)-1, n_frames, dtype=int)
    
    y = case["y"][idx]; v = case["v"][idx]; i = case["i"][idx]
    t_anim = t[idx]
    
    e_mech = case["E_mech"][idx]; e_L = case["E_L"][idx]; e_heat_total = case["E_heat_total"][idx]
    dphidz = np.array([params["dphi_dz_func"](y_val - params["z_coil"]) for y_val in y])
    emf = -params["N_turns"] * dphidz * v
    p_me2el = (params["N_turns"] * i * dphidz) * v
    if np.isfinite(case["Rext"]):
        p_heat_coil = (i*i)*params["R_coil"]
        p_heat_load = (i*i)*case["Rext"]
        p_heat_total = p_heat_coil + p_heat_load
    else:
        p_heat_coil = np.zeros_like(t_anim)
        p_heat_load = np.zeros_like(t_anim)
        p_heat_total = np.zeros_like(t_anim)

    y_mm = y * 1000.0
    e_total = e_mech + e_L + e_heat_total

    # Scene layout
    ymin = float(np.min(y)) - 0.02
    ymax = float(np.max(y)) + 0.02
    top_anchor = ymax + 0.01
    coil_y = params["z_coil"]
    magnet_h = 0.02
    magnet_w = min(0.8 * (2.0 * params["a"]), 0.03)
    coil_h = max(0.04, 4.0 * params["a"])
    wall = 0.004
    outer_half_w = params["a"] + wall
    inner_half_w = params["a"]

    # 简化图形设置以加快渲染
    fig = plt.figure(figsize=(12, 6))  # 减小图形尺寸
    gs = fig.add_gridspec(1, 2, width_ratios=[1.1, 2.1], wspace=0.28)
    ax_scene = fig.add_subplot(gs[0, 0])
    sgs = gs[0, 1].subgridspec(2, 3, wspace=0.35, hspace=0.35)
    ax_y = fig.add_subplot(sgs[0, 0])
    ax_v = fig.add_subplot(sgs[0, 1])
    ax_i = fig.add_subplot(sgs[0, 2])
    ax_e = fig.add_subplot(sgs[1, 0])
    ax_p = fig.add_subplot(sgs[1, 1])  # phase
    ax_em = fig.add_subplot(sgs[1, 2]) # EM diag

    # Left scene - 简化
    ax_scene.set_xlim(-0.06, 0.06)
    ax_scene.set_ylim(ymin, ymax + 0.05)
    ax_scene.set_xlabel("x (m)"); ax_scene.set_ylabel("y (m)")
    ax_scene.set_title(f"Spring-magnet-coil ( {case_label} )")
    ax_scene.grid(True, alpha=0.2)
    ax_scene.plot([-0.05, 0.05], [top_anchor, top_anchor], color="k", lw=3)  # top support

    # Sleeve coil (outer + inner)
    outer_rect = patches.Rectangle((-outer_half_w, coil_y - 0.5*coil_h), 2.0*outer_half_w, coil_h, ec="C0", fc=(0.1, 0.5, 1.0, 0.12), lw=2)
    inner_rect = patches.Rectangle((-inner_half_w, coil_y - 0.5*coil_h), 2.0*inner_half_w, coil_h, ec="none", fc=ax_scene.get_facecolor())
    ax_scene.add_patch(outer_rect); ax_scene.add_patch(inner_rect)
    ax_scene.plot([-inner_half_w, -inner_half_w], [coil_y - 0.5*coil_h, coil_y + 0.5*coil_h], color="C0", lw=1, ls="--", alpha=0.6)
    ax_scene.plot([ inner_half_w,  inner_half_w], [coil_y - 0.5*coil_h, coil_y + 0.5*coil_h], color="C0", lw=1, ls="--", alpha=0.6)

    # Magnet (no rounded corners)
    magnet = patches.Rectangle((-magnet_w/2, y[0] - magnet_h/2), magnet_w, magnet_h, ec="C3", fc="tab:red", alpha=0.95, lw=1.5)
    ax_scene.add_patch(magnet)
    spring_line, = ax_scene.plot([], [], color="gray", lw=1.6)

    # 简化的绘图设置
    ax_y.set_title("y-t"); ax_y.set_xlabel("t (s)"); ax_y.set_ylabel("y (mm)"); ax_y.grid(True, alpha=0.3)
    ax_v.set_title("v-t"); ax_v.set_xlabel("t (s)"); ax_v.set_ylabel("v (m/s)"); ax_v.grid(True, alpha=0.3)
    ax_i.set_title("i-t"); ax_i.set_xlabel("t (s)"); ax_i.set_ylabel("i (A)");   ax_i.grid(True, alpha=0.3)
    
    # 只绘制轨迹，不绘制完整的灰色背景线
    line_y, = ax_y.plot([], [], color="C2", lw=2); dot_y, = ax_y.plot([], [], "o", color="C2", ms=5)
    line_v, = ax_v.plot([], [], color="C1", lw=2); dot_v, = ax_v.plot([], [], "o", color="C1", ms=5)
    line_i, = ax_i.plot([], [], color="C0", lw=2); dot_i, = ax_i.plot([], [], "o", color="C0", ms=5)

    # 设置坐标轴范围
    ax_y.set_xlim(t_anim[0], t_anim[-1]); ax_y.set_ylim(np.min(y_mm)*1.1, np.max(y_mm)*1.1)
    ax_v.set_xlim(t_anim[0], t_anim[-1]); ax_v.set_ylim(np.min(v)*1.1,    np.max(v)*1.1 if np.max(v)!=0 else 1.0)
    ax_i.set_xlim(t_anim[0], t_anim[-1]); ax_i.set_ylim(np.min(i)*1.1,    np.max(i)*1.1 if np.max(i)!=0 else 1.0)

    # 能量图
    ax_e.set_title("Energy"); ax_e.set_xlabel("t (s)"); ax_e.set_ylabel("J"); ax_e.grid(True, alpha=0.3)
    line_Em, = ax_e.plot([], [], color="C3", lw=2, label="E_mech")
    line_EL, = ax_e.plot([], [], color="C4", lw=2, label="E_L")
    line_Eh, = ax_e.plot([], [], color="C5", lw=2, label="Heat_total")
    line_Et, = ax_e.plot([], [], color="k",  lw=2, label="E_total")
    ax_e.legend(loc="best", fontsize=7)
    e_min = min(np.min(e_mech), np.min(e_L), np.min(e_heat_total), np.min(e_total))
    e_max = max(np.max(e_mech), np.max(e_L), np.max(e_heat_total), np.max(e_total))
    pad = 0.05*(e_max - e_min + 1e-12)
    ax_e.set_xlim(t_anim[0], t_anim[-1]); ax_e.set_ylim(e_min - pad, e_max + pad)

    # 相位图
    ax_p.set_title("phase y-v"); ax_p.set_xlabel("y (mm)"); ax_p.set_ylabel("v (m/s)"); ax_p.grid(True, alpha=0.3)
    line_p, = ax_p.plot([], [], color="C6", lw=2); dot_p, = ax_p.plot([], [], "o", color="C6", ms=5)
    ax_p.set_xlim(np.min(y_mm)*1.1, np.max(y_mm)*1.1); ax_p.set_ylim(np.min(v)*1.1, np.max(v)*1.1 if np.max(v)!=0 else 1.0)

    # EM图
    ax_em.set_title("EM diag"); ax_em.set_xlabel("t (s)"); ax_em.set_ylabel("V / W"); ax_em.grid(True, alpha=0.3)
    line_emf, = ax_em.plot([], [], color="C7", lw=2, label="EMF")
    line_pme, = ax_em.plot([], [], color="C8", lw=2, label="P_me->el")
    line_ph,  = ax_em.plot([], [], color="C9", lw=2, label="P_heat")
    ax_em.legend(loc="best", fontsize=7)
    em_min = min(np.min(emf), np.min(p_me2el), np.min(p_heat_total))
    em_max = max(np.max(emf), np.max(p_me2el), np.max(p_heat_total))
    em_pad = 0.05*(em_max - em_min + 1e-12)
    ax_em.set_xlim(t_anim[0], t_anim[-1]); ax_em.set_ylim(em_min - em_pad, em_max + em_pad)

    # Init/update
    def init():
        xs, ys = spring_polyline(top_anchor, y[0])
        spring_line.set_data(xs, ys)
        magnet.set_y(y[0] - magnet_h/2)
        for ln in (line_y, line_v, line_i, line_Em, line_EL, line_Eh, line_Et, line_p, line_emf, line_pme, line_ph):
            ln.set_data([], [])
        for d in (dot_y, dot_v, dot_i, dot_p):
            d.set_data([], [])
        return (spring_line, magnet, line_y, dot_y, line_v, dot_v, line_i, dot_i,
                line_Em, line_EL, line_Eh, line_Et, line_p, dot_p, line_emf, line_pme, line_ph)

    def update(frame_i):
        if stop_event and stop_event.is_set():
            return (spring_line, magnet)
            
        xs, ys = spring_polyline(top_anchor, y[frame_i], width=0.02)
        spring_line.set_data(xs, ys)
        magnet.set_y(y[frame_i] - magnet_h/2)
        
        # traces
        line_y.set_data(t_anim[:frame_i+1], y_mm[:frame_i+1]); dot_y.set_data([t_anim[frame_i]], [y_mm[frame_i]])
        line_v.set_data(t_anim[:frame_i+1], v[:frame_i+1]);    dot_v.set_data([t_anim[frame_i]], [v[frame_i]])
        line_i.set_data(t_anim[:frame_i+1], i[:frame_i+1]);    dot_i.set_data([t_anim[frame_i]], [i[frame_i]])
        line_Em.set_data(t_anim[:frame_i+1], e_mech[:frame_i+1])
        line_EL.set_data(t_anim[:frame_i+1], e_L[:frame_i+1])
        line_Eh.set_data(t_anim[:frame_i+1], e_heat_total[:frame_i+1])
        line_Et.set_data(t_anim[:frame_i+1], e_total[:frame_i+1])
        line_p.set_data(y_mm[:frame_i+1], v[:frame_i+1]); dot_p.set_data([y_mm[frame_i]], [v[frame_i]])
        line_emf.set_data(t_anim[:frame_i+1], emf[:frame_i+1])
        line_pme.set_data(t_anim[:frame_i+1], p_me2el[:frame_i+1])
        line_ph.set_data(t_anim[:frame_i+1], p_heat_total[:frame_i+1])
        return (spring_line, magnet, line_y, dot_y, line_v, dot_v, line_i, dot_i,
                line_Em, line_EL, line_Eh, line_Et, line_p, dot_p, line_emf, line_pme, line_ph)

    ani = animation.FuncAnimation(fig, update, frames=len(t_anim), init_func=init, blit=True, interval=1000.0/fps)

    # 保存GIF - 使用快速设置
    try:
        gif_path = f"{out_base}.gif"
        print(f"Saving GIF -> {gif_path}")
        writer = animation.PillowWriter(fps=fps)
        bar = ProgressBar(total=len(t_anim), desc="Rendering GIF", ui_cb=ui_cb, stop_event=stop_event)
        
        # 使用更快的保存设置
        ani.save(gif_path, writer=writer, dpi=100,  # 降低DPI
                progress_callback=lambda i, n: (bar.update_to(i+1), None) if bar else None)
        bar.close()
        out_gif = gif_path
    except Exception as e:
        plt.close(fig)
        raise RuntimeError(f"GIF save failed: {e}")

    plt.close(fig)
    return None, out_gif  # 只返回GIF路径

# ---------- One run pipeline ----------
def run_simulation(params, ui_cb=None, output_callback=None, stop_event=None, time_callback=None):
    # 重定向输出到GUI
    old_stdout = sys.stdout
    if output_callback:
        sys.stdout = OutputRedirector(output_callback)
    
    try:
        # 初始化dphi_dz缓存函数
        params["dphi_dz_func"] = CachedDPhiDZ(params["mu0"], params["m_dipole"], params["a"])
        
        # 显示使用的优化方法
        if USE_NUMBA and not params.get("fast_mode", False):
            print("使用Numba JIT编译加速...")
        elif params.get("fast_mode", False):
            print("使用快速模式...")
        else:
            print("使用标准模式...")
        
        # Derive time base
        Rext_vals = params["Rext_cases"]
        dt, T_mech, tau_min = choose_dt(params, [r for r in Rext_vals if np.isfinite(r)])
        
        # 快速模式调整
        if params.get("fast_mode", False):
            # 增加时间步长
            dt = min(dt * 2, params.get("dt_cap", 5.0e-5))
            # 减少总步数
            max_steps = min(int(params["t_end"] / dt) + 1, 50000)
            t = np.linspace(0.0, params["t_end"], max_steps)
        else:
            num_steps = int(params["t_end"] / dt) + 1
            t = np.linspace(0.0, params["t_end"], num_steps)

        print("Integration settings:")
        print(f"  T_mech ~ {T_mech:.6f} s, tau_min ~ {tau_min:.6e} s")
        print(f"  dt = {dt:.6e} s, steps = {len(t)}")
        print(f"  R_coil = {params['R_coil']} ohm")

        # Integrate cases
        results = {}
        for i, Rext in enumerate(Rext_vals):
            if stop_event and stop_event.is_set():
                print("模拟被用户停止")
                break
                
            if np.isfinite(Rext):
                Rtot = params["R_coil"] + Rext
                label = f"Rext={Rext:g} ohm (Rtot={Rtot:g} ohm)"
                print(f"Solving case: {label}")
                
                # 计算预计时间
                start_time = time.time()
                case = integrate_case(params, Rext, t, dt, desc=f"Integrating {label}", 
                                     ui_cb=ui_cb, stop_event=stop_event)
                elapsed = time.time() - start_time
                
                # 更新剩余时间估计
                remaining_cases = len(Rext_vals) - i - 1
                estimated_remaining = elapsed * remaining_cases if remaining_cases > 0 else 0
                if time_callback:
                    time_callback(estimated_remaining)
            else:
                label = "Rext=open (Rtot=inf ohm)"
                print(f"Solving case: {label}")
                
                # 计算预计时间
                start_time = time.time()
                case = integrate_open(params, t, dt, desc=f"Integrating {label}", 
                                     ui_cb=ui_cb, stop_event=stop_event)
                elapsed = time.time() - start_time
                
                # 更新剩余时间估计
                remaining_cases = len(Rext_vals) - i - 1
                estimated_remaining = elapsed * remaining_cases if remaining_cases > 0 else 0
                if time_callback:
                    time_callback(estimated_remaining)
                    
            results[label] = case

        if stop_event and stop_event.is_set():
            print("模拟提前结束")
            return None

        # Static comparisons across cases
        labels = list(results.keys())
        ys_mm = [results[k]["y"]*1000.0 for k in labels]
        vs     = [results[k]["v"] for k in labels]
        is_    = [results[k]["i"] for k in labels]

        save_zoom_plot(t, ys_mm, labels, "Time (s)", "Displacement y (mm)",
                       "y-t (displacement)", "fig_y_t.png", "fig_y_t_zoom.png", params["t_zoom"])
        save_zoom_plot(t, vs, labels, "Time (s)", "Velocity v (m/s)",
                       "v-t (velocity)", "fig_v_t.png", "fig_v_t_zoom.png", params["t_zoom"])
        save_zoom_plot(t, is_, labels, "Time (s)", "Coil current i (A)",
                       "i-t (current)", "fig_i_t.png", "fig_i_t_zoom.png", params["t_zoom"])

        # Focus case: choose first finite Rext if available else first
        focus_key = None
        for k in labels:
            if "Rext=open" not in k:
                focus_key = k; break
        if focus_key is None:
            focus_key = labels[0]
        case = results[focus_key]

        # Energy
        plt.figure(figsize=(10, 5))
        plt.plot(t, case["E_mech"], label="Mechanical (T+U)")
        plt.plot(t, case["E_L"],    label="Magnetic (0.5 L i^2)")
        plt.plot(t, case["E_heat_total"], label="Heat total")
        plt.plot(t, case["E_total"], "--", label="Total (~const)")
        plt.xlabel("Time (s)"); plt.ylabel("Energy (J)")
        plt.title(f"Energy transfer ({focus_key})")
        plt.grid(True, alpha=0.35); plt.legend(); plt.tight_layout()
        plt.savefig(f"fig_energy_{focus_key.replace(' ','_')}.png", dpi=140)

        # Phase
        plt.figure(figsize=(5.5, 5.5))
        plt.plot(case["y"]*1000.0, case["v"], lw=1.0)
        plt.xlabel("y (mm)"); plt.ylabel("v (m/s)")
        plt.title(f"Phase plot y-v ({focus_key})")
        plt.grid(True, alpha=0.35); plt.tight_layout()
        plt.savefig(f"fig_phase_{focus_key.replace(' ','_')}.png", dpi=140)

        # EM diag
        dphidz = np.array([params["dphi_dz_func"](y_val - params["z_coil"]) for y_val in case["y"]])
        emf = -params["N_turns"] * dphidz * case["v"]
        p_me2el = (params["N_turns"] * case["i"] * dphidz) * case["v"]
        if np.isfinite(case["Rext"]):
            p_heat_total = (case["i"]*case["i"])*(params["R_coil"] + case["Rext"])
        else:
            p_heat_total = np.zeros_like(t)
        plt.figure(figsize=(10, 5))
        plt.plot(t, emf, label="EMF (V)")
        plt.plot(t, p_me2el, label="Power mech->elec (W)")
        plt.plot(t, p_heat_total, label="Heat power total (W)")
        plt.xlabel("Time (s)"); plt.ylabel("EMF / Power")
        plt.title(f"EM coupling diagnostics ({focus_key})")
        plt.grid(True, alpha=0.35); plt.legend(); plt.tight_layout()
        plt.savefig(f"fig_em_coupling_{focus_key.replace(' ','_')}.png", dpi=140)

        # Animation
        if not (stop_event and stop_event.is_set()):
            mp4_path, gif_path = render_animation(params, t, case, case_label=focus_key,
                                                  fps=params["fps"], out_base=params["anim_base"], 
                                                  ui_cb=ui_cb, stop_event=stop_event)

            print("Saved images:")
            print("  fig_y_t.png, fig_y_t_zoom.png")
            print("  fig_v_t.png, fig_v_t_zoom.png")
            print("  fig_i_t.png, fig_i_t_zoom.png")
            print(f"  fig_energy_{focus_key.replace(' ','_')}.png")
            print(f"  fig_phase_{focus_key.replace(' ','_')}.png")
            print(f"  fig_em_coupling_{focus_key.replace(' ','_')}.png")
            if mp4_path:
                print(f"Animation MP4: {mp4_path}")
            print(f"Animation GIF: {gif_path}")
            
            return gif_path  # 返回GIF路径用于在GUI中显示
        
        print("\n=== 模拟完成 ===")
        return None
        
    except StopIteration as e:
        print(f"\n模拟被用户停止: {e}")
        return None
    finally:
        # 恢复标准输出
        sys.stdout = old_stdout

# 输出重定向类
class OutputRedirector:
    def __init__(self, callback):
        self.callback = callback
        self.buffer = ""
        
    def write(self, text):
        self.buffer += text
        # 按行处理输出
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line.strip():  # 忽略空行
                self.callback(line + '\n')
                
    def flush(self):
        # 处理缓冲区中剩余的内容
        if self.buffer:
            self.callback(self.buffer + '\n')
            self.buffer = ""

# ---------- Default parameters ----------
def default_params():
    return {
        # Mechanical
        "m": 0.05,         # kg
        "k": 20.0,         # N/m
        # EM + geometry
        "mu0": 4.0e-7*np.pi,
        "m_dipole": 0.30,  # A*m^2
        "N_turns": 500,
        "a": 0.010,        # m, inner radius
        "L_coil": 1.0e-3,  # H
        "R_coil": 2.0,     # ohm, fixed series resistance
        "z_coil": 0.0,     # m
        # Initial
        "y0": 0.030,       # m
        "v0": 0.0,         # m/s
        # Time
        "t_end": 8.0,      # s
        # Plot/anim
        "fps": 30,
        "t_zoom": 0.5,     # s
        "anim_base": "sim_animation",
        # Step control
        "dt_cap": 5.0e-5,
        "elec_divisor": 20.0,
        "mech_steps_per_period": 2000.0,
        # Cases (external loads); 'np.inf' means open circuit baseline
        "Rext_cases": [5.0, 0.5, np.inf],
        # 优化选项
        "fast_mode": False,
        "use_scipy": False,
    }

# ---------- GUI (Tkinter) ----------
def launch_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
    from PIL import Image, ImageTk
    import os

    p = default_params()

    root = tk.Tk()
    root.title("Spring-Magnet-Coil Simulator")
    root.geometry("1000x750")

    # 创建主框架
    main = ttk.Frame(root, padding=8)
    main.grid(row=0, column=0, sticky="nsew")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)
    
    # 创建左右分栏
    left_frame = ttk.Frame(main)
    left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    
    right_frame = ttk.Frame(main)
    right_frame.grid(row=0, column=1, sticky="nsew")
    
    main.columnconfigure(0, weight=1)
    main.columnconfigure(1, weight=1)
    main.rowconfigure(0, weight=1)

    # 左侧：参数输入
    def add_entry(parent, row, col, label, var, width=12):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=4, pady=2)
        e = ttk.Entry(parent, textvariable=var, width=width)
        e.grid(row=row, column=col+1, sticky="we", padx=4, pady=2)
        return e

    # 变量
    v_m = tk.StringVar(value=str(p["m"]))
    v_k = tk.StringVar(value=str(p["k"]))
    v_md = tk.StringVar(value=str(p["m_dipole"]))
    v_N  = tk.StringVar(value=str(p["N_turns"]))
    v_a  = tk.StringVar(value=str(p["a"]))
    v_L  = tk.StringVar(value=str(p["L_coil"]))
    v_Rc = tk.StringVar(value=str(p["R_coil"]))
    v_y0 = tk.StringVar(value=str(p["y0"]))
    v_v0 = tk.StringVar(value=str(p["v0"]))
    v_tend = tk.StringVar(value=str(p["t_end"]))
    v_fps = tk.StringVar(value=str(p["fps"]))
    v_zoom = tk.StringVar(value=str(p["t_zoom"]))
    v_dtcap = tk.StringVar(value=str(p["dt_cap"]))
    v_ediv = tk.StringVar(value=str(p["elec_divisor"]))
    v_msteps = tk.StringVar(value=str(p["mech_steps_per_period"]))
    v_Rext = tk.StringVar(value="5,0.5,open")
    v_anim = tk.StringVar(value=p["anim_base"])
    
    # 优化选项
    v_fast_mode = tk.BooleanVar(value=p["fast_mode"])
    v_use_scipy = tk.BooleanVar(value=p["use_scipy"])

    # 添加输入框
    add_entry(left_frame, 0, 0, "质量 m (kg):", v_m)
    add_entry(left_frame, 1, 0, "弹簧常数 k (N/m):", v_k)
    add_entry(left_frame, 2, 0, "磁偶极矩 m_dipole (A*m^2):", v_md)
    add_entry(left_frame, 3, 0, "线圈匝数 N_turns:", v_N)
    add_entry(left_frame, 4, 0, "线圈半径 a (m):", v_a)
    add_entry(left_frame, 5, 0, "电感 L_coil (H):", v_L)
    add_entry(left_frame, 6, 0, "线圈电阻 R_coil (ohm):", v_Rc)
    add_entry(left_frame, 7, 0, "初始位移 y0 (m):", v_y0)
    add_entry(left_frame, 8, 0, "初始速度 v0 (m/s):", v_v0)
    add_entry(left_frame, 9, 0, "模拟时间 t_end (s):", v_tend)
    add_entry(left_frame, 10, 0, "帧率 fps:", v_fps)
    add_entry(left_frame, 11, 0, "缩放时间 t_zoom (s):", v_zoom)
    add_entry(left_frame, 12, 0, "时间步长上限 dt_cap:", v_dtcap)
    add_entry(left_frame, 13, 0, "电气分割因子 elec_divisor:", v_ediv)
    add_entry(left_frame, 14, 0, "机械步数/周期 mech_steps_per_period:", v_msteps)
    add_entry(left_frame, 15, 0, "外部电阻 Rext (逗号分隔):", v_Rext)
    add_entry(left_frame, 16, 0, "动画文件名:", v_anim)
    
    # 优化选项
    ttk.Checkbutton(left_frame, text="快速模式 (减少精度提高速度)", variable=v_fast_mode).grid(
        row=17, column=0, columnspan=2, sticky="w", pady=2)
    
    if USE_SCIPY:
        ttk.Checkbutton(left_frame, text="使用Scipy ODE求解器", variable=v_use_scipy).grid(
            row=18, column=0, columnspan=2, sticky="w", pady=2)
    else:
        ttk.Label(left_frame, text="安装scipy可使用更快的ODE求解器").grid(
            row=18, column=0, columnspan=2, sticky="w", pady=2)

    # 进度条
    progress_label = ttk.Label(left_frame, text="进度: 等待开始")
    progress_label.grid(row=19, column=0, columnspan=2, sticky="w", pady=(10, 0))
    
    progress_bar = ttk.Progressbar(left_frame, mode='determinate')
    progress_bar.grid(row=20, column=0, columnspan=2, sticky="we", pady=5)
    
    # 剩余时间标签
    time_label = ttk.Label(left_frame, text="预计剩余时间: --")
    time_label.grid(row=21, column=0, columnspan=2, sticky="w", pady=5)

    # 按钮框架
    button_frame = ttk.Frame(left_frame)
    button_frame.grid(row=22, column=0, columnspan=2, pady=10)
    
    run_button = ttk.Button(button_frame, text="运行模拟")
    run_button.pack(side=tk.LEFT, padx=(0, 10))
    
    stop_button = ttk.Button(button_frame, text="停止模拟", state=tk.DISABLED)
    stop_button.pack(side=tk.LEFT)

    # 右侧：输出文本框和GIF显示
    right_top_frame = ttk.Frame(right_frame)
    right_top_frame.grid(row=0, column=0, sticky="nsew")
    
    right_bottom_frame = ttk.Frame(right_frame)
    right_bottom_frame.grid(row=1, column=0, sticky="nsew")
    
    right_frame.columnconfigure(0, weight=1)
    right_frame.rowconfigure(0, weight=1)
    right_frame.rowconfigure(1, weight=1)
    
    # 输出文本框
    output_label = ttk.Label(right_top_frame, text="模拟输出:")
    output_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
    
    output_text = scrolledtext.ScrolledText(right_top_frame, width=60, height=15, wrap=tk.WORD)
    output_text.grid(row=1, column=0, sticky="nsew")
    output_text.config(state=tk.DISABLED)
    
    right_top_frame.columnconfigure(0, weight=1)
    right_top_frame.rowconfigure(1, weight=1)
    
    # GIF显示区域
    gif_label = ttk.Label(right_bottom_frame, text="动画将在这里显示")
    gif_label.grid(row=0, column=0, sticky="nsew", pady=10)
    
    right_bottom_frame.columnconfigure(0, weight=1)
    right_bottom_frame.rowconfigure(0, weight=1)

    # GIF动画相关变量 - 确保在函数外部定义
    gif_frames = []
    current_gif_frame = 0
    gif_animation_id = None  # 确保在函数开始处初始化

    def display_gif(gif_path):
        """在GUI中显示GIF动画"""
        nonlocal gif_frames, current_gif_frame, gif_animation_id
        
        # 停止之前的动画
        if gif_animation_id is not None:
            root.after_cancel(gif_animation_id)
            gif_animation_id = None
        
        if not os.path.exists(gif_path):
            gif_label.config(text="GIF文件未找到")
            return
            
        try:
            # 加载GIF帧
            gif_frames = []
            gif = Image.open(gif_path)
            
            # 调整GIF大小以适应显示区域
            max_size = (400, 300)
            for frame in range(0, gif.n_frames):
                gif.seek(frame)
                frame_image = gif.copy()
                frame_image.thumbnail(max_size, Image.Resampling.LANCZOS)
                gif_frames.append(ImageTk.PhotoImage(frame_image))
            
            if gif_frames:
                current_gif_frame = 0
                gif_label.config(image=gif_frames[0])
                animate_gif()
            else:
                gif_label.config(text="无法加载GIF帧")
                
        except Exception as e:
            gif_label.config(text=f"加载GIF错误: {str(e)}")

    def animate_gif():
        """动画循环"""
        nonlocal current_gif_frame, gif_animation_id
        
        if not gif_frames:
            return
            
        current_gif_frame = (current_gif_frame + 1) % len(gif_frames)
        gif_label.config(image=gif_frames[current_gif_frame])
        
        # 计划下一帧 (大约100ms延迟，即10fps)
        gif_animation_id = root.after(100, animate_gif)

    # 输出到文本框的函数
    def append_output(text):
        output_text.config(state=tk.NORMAL)
        output_text.insert(tk.END, text)
        output_text.see(tk.END)
        output_text.config(state=tk.DISABLED)
        output_text.update_idletasks()

    # 停止事件
    stop_event = threading.Event()

    # 进度更新函数
    def update_progress(desc, progress):
        progress_bar['value'] = progress * 100
        progress_label.config(text=f"进度: {desc} - {progress*100:.1f}%")
        root.update_idletasks()

    # 剩余时间更新函数
    def update_remaining_time(remaining_seconds):
        if remaining_seconds > 0:
            if remaining_seconds < 60:
                time_str = f"{remaining_seconds:.0f}秒"
            elif remaining_seconds < 3600:
                time_str = f"{remaining_seconds/60:.1f}分钟"
            else:
                time_str = f"{remaining_seconds/3600:.1f}小时"
            time_label.config(text=f"预计剩余时间: {time_str}")
        else:
            time_label.config(text="预计剩余时间: 计算中...")
        root.update_idletasks()

    # 清空输出
    def clear_output():
        nonlocal gif_animation_id, gif_frames, current_gif_frame
        
        output_text.config(state=tk.NORMAL)
        output_text.delete(1.0, tk.END)
        output_text.config(state=tk.DISABLED)
        
        # 清除GIF显示
        if gif_animation_id is not None:
            root.after_cancel(gif_animation_id)
            gif_animation_id = None
            
        gif_frames = []
        current_gif_frame = 0
        gif_label.config(image='', text="动画将在这里显示")

    # 运行模拟的函数
    def run_simulation_thread():
        nonlocal gif_animation_id
        
        try:
            # 禁用运行按钮，启用停止按钮
            run_button.config(state=tk.DISABLED)
            stop_button.config(state=tk.NORMAL)
            stop_event.clear()
            clear_output()
            
            params = default_params()
            params["m"] = float(v_m.get())
            params["k"] = float(v_k.get())
            params["m_dipole"] = float(v_md.get())
            params["N_turns"] = int(v_N.get())
            params["a"] = float(v_a.get())
            params["L_coil"] = float(v_L.get())
            params["R_coil"] = float(v_Rc.get())
            params["y0"] = float(v_y0.get())
            params["v0"] = float(v_v0.get())
            params["t_end"] = float(v_tend.get())
            params["fps"] = int(v_fps.get())
            params["t_zoom"] = float(v_zoom.get())
            params["dt_cap"] = float(v_dtcap.get())
            params["elec_divisor"] = float(v_ediv.get())
            params["mech_steps_per_period"] = float(v_msteps.get())
            params["Rext_cases"] = [float(x) if x != "open" else np.inf for x in v_Rext.get().split(",")]
            params["anim_base"] = v_anim.get()
            params["fast_mode"] = v_fast_mode.get()
            params["use_scipy"] = v_use_scipy.get()

            # 运行模拟
            gif_path = run_simulation(params, ui_cb=update_progress, output_callback=append_output, 
                          stop_event=stop_event, time_callback=update_remaining_time)
            
            # 显示GIF
            if gif_path and os.path.exists(gif_path):
                root.after(0, lambda: display_gif(gif_path))
            
            messagebox.showinfo("完成", "模拟已完成！")
            
        except Exception as e:
            append_output(f"错误: {str(e)}\n")
            messagebox.showerror("错误", f"模拟失败：{e}")
        finally:
            # 重新启用运行按钮，禁用停止按钮
            run_button.config(state=tk.NORMAL)
            stop_button.config(state=tk.DISABLED)
            progress_bar['value'] = 0
            progress_label.config(text="进度: 完成")
            time_label.config(text="预计剩余时间: --")

    def on_run():
        # 在新线程中运行模拟，避免阻塞GUI
        thread = threading.Thread(target=run_simulation_thread)
        thread.daemon = True
        thread.start()

    def on_stop():
        stop_event.set()
        append_output("用户请求停止模拟...\n")

    run_button.config(command=on_run)
    stop_button.config(command=on_stop)

    root.mainloop()
   
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--gui":
        launch_gui()  # 启动 GUI 模式
    else:
        params = default_params()
        run_simulation(params)  # 运行模拟