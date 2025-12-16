# mach_ring_sim.py
# 2D Euler (HLLE) underexpanded jet from a parameterized Laval nozzle
# Phase 1: compute all frames (with progress bar; physical-time driven)
# Phase 2: play animation of precomputed schlieren frames and Mach ring markers

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import animation

# -----------------------------
# User‑tweakable parameters
# -----------------------------
# Domain enlarged to show more Mach rings
Lx, Ly = 160.0, 20.0
NX, NY = 720, 240            # moderate grid; increase for sharper shocks

# Time control (physical-time driven sampling)
CFL = 0.55                   # slight increase; reduce if unstable
T_END = 120.0                 # total physical time to simulate
OUTPUT_FPS = 20              # saved frames per physical second (sampling rate)
FRAMES = int(T_END * OUTPUT_FPS + 0.5)
CAPTURE_T0 = False           # if True, store a frame at t=0

# Gas
GAMMA = 1.4
R_GAS = 1.0

# Ambient and jet (underexpanded: P_JET > P_AMB)
P_AMB = 1.0
T_AMB = 1.0
T_JET = 2.0
P_JET = 3.0
M_JET = 2.4

# Laval nozzle geometry (half-height h(x))
L_NOZ = 3.0      # total nozzle length
X_CONV = 1.2     # end of converging section
H_IN = 0.9       # inlet half-height
H_TH = 0.35      # throat half-height (min)
H_EX = 1.6       # exit half-height

# Plate at the very left (optional visual hint)
PLATE_THICK = 0.03

# Output / animation
SAVE_MP4 = False
MP4_NAME = "mach_ring.mp4"
PLAYBACK_FPS = 30            # playback fps for animation

# Mach ring marker settings
MAX_MARKS = 12
PEAK_MIN_DIST_FRACTION = 0.04  # of NX
PEAK_THR_REL = 0.55

# -----------------------------
# Discretization, state arrays
# -----------------------------
dx, dy = Lx / NX, Ly / NY
x = (np.arange(NX) + 0.5) * dx
y = (np.arange(NY) + 0.5) * dy
X, Y = np.meshgrid(x, y)
yc = Ly * 0.5

# Conserved variables with 1 ghost cell on each side: [rho, rho*u, rho*v, E]
# Use float32 for speed and lower memory footprint
U = np.zeros((NY + 2, NX + 2, 4), dtype=np.float32)
IDX = slice(1, NY + 1)
JDX = slice(1, NX + 1)

# -----------------------------
# Helpers: primitives/fluxes
# -----------------------------
def prim_to_cons(rho, u, v, p):
    E = p / (GAMMA - 1.0) + 0.5 * rho * (u*u + v*v)
    return np.stack([rho, rho*u, rho*v, E], axis=-1).astype(np.float32)

def cons_to_prim(Uc):
    rho = Uc[..., 0]
    inv_rho = 1.0 / np.maximum(rho, 1e-12)
    u = Uc[..., 1] * inv_rho
    v = Uc[..., 2] * inv_rho
    e = Uc[..., 3] - 0.5 * rho * (u*u + v*v)
    p = (GAMMA - 1.0) * e
    p = np.maximum(p, 1e-6)
    return rho, u, v, p

def flux_x(rho, u, v, p, E):
    return np.stack([rho*u, rho*u*u + p, rho*u*v, (E + p)*u], axis=-1)

def flux_y(rho, u, v, p, E):
    return np.stack([rho*v, rho*v*u, rho*v*v + p, (E + p)*v], axis=-1)

def sound_speed(p, rho):
    return np.sqrt(GAMMA * np.maximum(p, 1e-12) / np.maximum(rho, 1e-12))

def hlle_flux(U_L, U_R, axis=0):
    rhoL, uL, vL, pL = cons_to_prim(U_L)
    rhoR, uR, vR, pR = cons_to_prim(U_R)
    EL, ER = U_L[..., 3], U_R[..., 3]
    aL = sound_speed(pL, rhoL)
    aR = sound_speed(pR, rhoR)

    if axis == 0:
        sL = np.minimum(uL - aL, uR - aR)
        sR = np.maximum(uL + aL, uR + aR)
        FL = flux_x(rhoL, uL, vL, pL, EL)
        FR = flux_x(rhoR, uR, vR, pR, ER)
    else:
        sL = np.minimum(vL - aL, vR - aR)
        sR = np.maximum(vL + aL, vR + aR)
        FL = flux_y(rhoL, uL, vL, pL, EL)
        FR = flux_y(rhoR, uR, vR, pR, ER)

    denom = np.where((sR - sL) != 0.0, sR - sL, 1e-12)
    F = (sR[..., None]*FL - sL[..., None]*FR + (sL*sR)[..., None]*(U_R - U_L)) / denom[..., None]
    F = np.where((sL >= 0.0)[..., None], FL, F)
    F = np.where((sR <= 0.0)[..., None], FR, F)
    return F.astype(np.float32)

# -----------------------------
# Nozzle geometry
# -----------------------------
def nozzle_half_height(xpos):
    # Smooth cosine transitions: 0..X_CONV converging, X_CONV..L_NOZ diverging
    xpos = np.asarray(xpos)
    h = np.full_like(xpos, H_EX, dtype=np.float32)
    m = xpos <= X_CONV
    if np.any(m):
        s = xpos[m] / max(X_CONV, 1e-9)
        h[m] = H_IN - 0.5*(H_IN - H_TH)*(1.0 - np.cos(np.pi*s)).astype(np.float32)
    m = (xpos > X_CONV) & (xpos <= L_NOZ)
    if np.any(m):
        s = (xpos[m] - X_CONV) / max(L_NOZ - X_CONV, 1e-9)
        h[m] = H_TH + 0.5*(H_EX - H_TH)*(1.0 - np.cos(np.pi*s)).astype(np.float32)
    # downstream: keep exit half-height
    return h.astype(np.float32)

h_x = nozzle_half_height(x)
y_top = yc + h_x
y_bot = yc - h_x

# -----------------------------
# States and BC
# -----------------------------
RHO_AMB = P_AMB / (R_GAS * T_AMB)
a_amb = np.sqrt(GAMMA * R_GAS * T_AMB).astype(np.float32)
U_amb = prim_to_cons(np.float32(RHO_AMB), 0.0, 0.0, np.float32(P_AMB))

a_jet = np.sqrt(GAMMA * R_GAS * T_JET).astype(np.float32)
u_jet = np.float32(M_JET) * a_jet
rho_jet = np.float32(P_JET / (R_GAS * T_JET))
U_in = prim_to_cons(rho_jet, u_jet, 0.0, np.float32(P_JET))

slot_y0 = yc - H_IN
slot_y1 = yc + H_IN

def apply_bc(U):
    # Top/bottom transmissive
    U[0, 1:-1, :] = U[1, 1:-1, :]
    U[-1, 1:-1, :] = U[-2, 1:-1, :]
    # Right transmissive
    U[1:-1, -1, :] = U[1:-1, -2, :]

    # Left boundary: supersonic inflow inside inlet slot; outside vertical wall
    ys = (np.arange(NY + 2) - 0.5) * dy
    in_slot = (ys >= slot_y0) & (ys <= slot_y1)
    U[in_slot, 0, :] = U_in
    rho, u, v, p = cons_to_prim(U[~in_slot, 1, :])
    U[~in_slot, 0, :] = prim_to_cons(rho, -u, v, p)

    # Thin vertical plate just inside domain
    plate_cols = max(1, int(PLATE_THICK / dx))
    if plate_cols > 0:
        j = slice(1, 1 + plate_cols)
        mask_vert = ~((y >= slot_y0) & (y <= slot_y1))[:, None]
        rho, u, v, p = cons_to_prim(U[IDX, j, :])
        u = np.where(mask_vert, -u, u)
        U[IDX, j, :] = prim_to_cons(rho, u, v, p)

def apply_internal_nozzle_walls(U):
    # Slip walls within 0..L_NOZ: reflect vertical velocity outside local channel
    j_end = min(NX, int(L_NOZ / dx))
    if j_end <= 0:
        return
    Ub = U[IDX, 1:1+j_end, :]
    rho, u, v, p = cons_to_prim(Ub)
    hj = nozzle_half_height(x[:j_end])
    Ygrid = y[:, None]
    mask = (Ygrid > (yc + hj)[None, :]) | (Ygrid < (yc - hj)[None, :])
    v = np.where(mask, -v, v)  # reflect across horizontal walls (slip)
    U[IDX, 1:1+j_end, :] = prim_to_cons(rho, u, v, p)

def compute_dt(U):
    rho, u, v, p = cons_to_prim(U[IDX, JDX, :])
    a = sound_speed(p, rho)
    sx = float(np.max(np.abs(u) + a))
    sy = float(np.max(np.abs(v) + a))
    sx = max(sx, 1e-8)
    sy = max(sy, 1e-8)
    return np.float32(CFL * min(dx / sx, dy / sy))

def apply_sponge(U, dt):
    # Simple sponge near top/bottom/right to reduce reflections
    sponge_w = int(0.18 * min(NX, NY))
    if sponge_w < 2:
        return
    smax = 1.0 / max(0.6, 0.2 * (Lx / float(a_amb)))
    sig = np.zeros((NY, NX), dtype=np.float32)
    wy = np.linspace(0, 1, sponge_w, dtype=np.float32)
    sig[:sponge_w, :] = wy[::-1, None] * smax
    sig[-sponge_w:, :] = wy[:, None] * smax
    wx = np.linspace(0, 1, sponge_w, dtype=np.float32)
    sig[:, -sponge_w:] = np.maximum(sig[:, -sponge_w:], wx[None, :] * smax)
    damp = np.clip(sig * float(dt), 0.0, 0.5).astype(np.float32)
    Uc = U[IDX, JDX, :]
    U[IDX, JDX, :] = (1.0 - damp[..., None]) * Uc + damp[..., None] * U_amb

# -----------------------------
# Visualization helpers
# -----------------------------
def schlieren(U):
    # Density-gradient-based schlieren (log stretch, per-frame normalized)
    rho, u, v, p = cons_to_prim(U[IDX, JDX, :])
    drdx = (np.pad(rho, ((0,0),(1,1)), mode='edge')[:, 2:] -
            np.pad(rho, ((0,0),(1,1)), mode='edge')[:, :-2]) / (2*dx)
    drdy = (np.pad(rho, ((1,1),(0,0)), mode='edge')[2:, :] -
            np.pad(rho, ((1,1),(0,0)), mode='edge')[:-2, :]) / (2*dy)
    g = np.abs(drdx) + np.abs(drdy)
    s = np.log10(g + 1e-6)
    smin, smax = np.percentile(s, 5), np.percentile(s, 99.5)
    s = (s - smin) / max(smax - smin, 1e-6)
    return np.clip(s, 0.0, 1.0).astype(np.float32)

def find_centerline_peaks(s2d, min_dist_cells, thr_rel, x_min):
    ic = int(np.argmin(np.abs(y - yc)))
    s = s2d[ic, :].copy()
    j_min = int(x_min / dx)
    s[:j_min] = 0.0
    # light smoothing
    if s.size > 5:
        k = 5
        s = np.convolve(s, np.ones(k, dtype=np.float32)/k, mode='same')
    thr = thr_rel * (np.max(s) if np.max(s) > 1e-8 else 1.0)
    idx = []
    for j in range(1, len(s)-1):
        if s[j] >= s[j-1] and s[j] >= s[j+1] and s[j] > thr:
            idx.append(j)
    picked = []
    for j in idx:
        if not picked or (j - picked[-1]) >= min_dist_cells:
            picked.append(j)
    x_peaks = (np.array(picked) + 0.5) * dx
    x_peaks = x_peaks[x_peaks > (L_NOZ + 0.2)]
    return x_peaks.astype(np.float32)

# -----------------------------
# Time stepping kernel (in-place)
# -----------------------------
def step(U):
    apply_bc(U)
    apply_internal_nozzle_walls(U)
    dt = compute_dt(U)

    # X-fluxes
    UL = U[IDX, 0:NX+1, :]
    UR = U[IDX, 1:NX+2, :]
    Fx = hlle_flux(UL, UR, axis=0)

    # Y-fluxes
    UL = U[0:NY+1, JDX, :]
    UR = U[1:NY+2, JDX, :]
    Fy = hlle_flux(UL, UR, axis=1)

    # In-place update to avoid heavy copies
    U[IDX, JDX, :] -= (dt / dx) * (Fx[:, 1:, :] - Fx[:, :-1, :])
    U[IDX, JDX, :] -= (dt / dy) * (Fy[1:, :, :] - Fy[:-1, :, :])

    # Ensure non-negative internal energy
    rho, u, v, p = cons_to_prim(U[IDX, JDX, :])
    E_min = p / (GAMMA - 1.0) + 0.5 * rho * (u*u + v*v)
    U[IDX, JDX, 3] = np.maximum(U[IDX, JDX, 3], E_min)

    apply_sponge(U, dt)
    return float(dt)

# -----------------------------
# Phase 1: Compute all frames (physical-time driven)
# -----------------------------
def compute_all_frames():
    # Initialize ambient
    U[IDX, JDX, :] = U_amb
    apply_bc(U)
    apply_internal_nozzle_walls(U)

    nframes = max(1, FRAMES)
    frames = np.zeros((nframes, NY, NX), dtype=np.float32)
    times = np.zeros(nframes, dtype=np.float64)
    peaks = np.full((nframes, MAX_MARKS), np.nan, dtype=np.float32)

    sample_dt = (1.0 / OUTPUT_FPS) if OUTPUT_FPS > 0 else (T_END / nframes)
    # If not capturing t=0, start sampling at sample_dt
    next_sample = 0.0 if CAPTURE_T0 else sample_dt
    k = 0
    sim_time = 0.0

    # Progress bar (by frames)
    try:
        from tqdm import tqdm
        pbar = tqdm(total=nframes, desc="Computing (frames)", ncols=80)
        use_pbar = True
    except Exception:
        use_pbar = False
        log_step = max(1, nframes // 10)

    # Advance until we collected all frames
    while k < nframes:
        dt = step(U)
        sim_time += dt

        # Capture frames whenever we pass the next sample time
        while k < nframes and sim_time >= next_sample - 1e-12:
            s2d = schlieren(U)
            frames[k, :, :] = s2d
            times[k] = sim_time

            x_peaks = find_centerline_peaks(
                s2d,
                min_dist_cells=int(PEAK_MIN_DIST_FRACTION * NX),
                thr_rel=PEAK_THR_REL,
                x_min=L_NOZ
            )
            n = min(len(x_peaks), MAX_MARKS)
            if n > 0:
                peaks[k, :n] = x_peaks[:n]

            k += 1
            next_sample += sample_dt
            if use_pbar:
                pbar.update(1)
            elif (k % log_step == 0 or k == nframes):
                print(f"Computing: frame {k}/{nframes}, t={sim_time:.2f}/{T_END:.2f}")

        # Optional early exit if time far exceeds T_END and we've sampled enough
        if sim_time >= T_END + 10.0 and k >= nframes:
            break

    if use_pbar:
        pbar.close()
    return frames, times, peaks

# -----------------------------
# Phase 2: Animate precomputed
# -----------------------------
def animate_frames(frames, times, peaks):
    fig, ax = plt.subplots(figsize=(16, 5))  # wider figure for larger Lx
    img = ax.imshow(
        frames[0],
        extent=[0, Lx, 0, Ly],
        origin='lower',
        cmap='gray',
        vmin=0, vmax=1,
        interpolation='nearest',
        animated=False
    )
    ax.set_title('Underexpanded Jet From Laval Nozzle – Schlieren-like')
    ax.set_xlabel('x')
    ax.set_ylabel('y')

    # Draw nozzle contour and inlet slot
    mask_noz = x <= L_NOZ
    ax.plot(x[mask_noz], y_top[mask_noz], color='cyan', lw=2, alpha=0.9)
    ax.plot(x[mask_noz], y_bot[mask_noz], color='cyan', lw=2, alpha=0.9)
    ax.plot([0, 0], [slot_y0, slot_y1], color='cyan', lw=3, alpha=0.9)

    time_text = ax.text(0.015, 0.96, f't = {times[0]:.3f}', transform=ax.transAxes, color='w')

    # Prepare marker artists
    mark_lines = []
    mark_labels = []
    for k in range(MAX_MARKS):
        ln, = ax.plot([0, 0], [0.0, Ly], ls='--', lw=1.2, color='yellow', alpha=0.85, visible=False)
        mark_lines.append(ln)
        txt = ax.text(0, Ly*0.98, '', ha='center', va='top', color='yellow', fontsize=8, visible=False)
        mark_labels.append(txt)

    def _set_markers(i):
        xs = peaks[i]  # length MAX_MARKS with NaNs
        for k in range(MAX_MARKS):
            xk = xs[k]
            vis = np.isfinite(xk)
            mark_lines[k].set_visible(vis)
            mark_labels[k].set_visible(vis)
            if vis:
                mark_lines[k].set_xdata([xk, xk])
                mark_labels[k].set_position((xk, Ly*0.98))
                mark_labels[k].set_text(f'MR{k+1}')

    def update(i):
        img.set_array(frames[i])
        time_text.set_text(f't = {times[i]:.3f}')
        _set_markers(i)
        return [img, time_text, *mark_lines, *mark_labels]

    ani = animation.FuncAnimation(fig, update, frames=len(times), interval=1000/PLAYBACK_FPS, blit=False)

    if SAVE_MP4:
        try:
            ani.save(MP4_NAME, fps=PLAYBACK_FPS, dpi=160, bitrate=5000)
            print(f"Saved {MP4_NAME}")
        except Exception as e:
            print("Failed to save mp4 (need ffmpeg?):", e)

    plt.tight_layout()
    plt.show()

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    frames, times, peaks = compute_all_frames()
    animate_frames(frames, times, peaks)
