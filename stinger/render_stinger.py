"""Ctrl+Bebo keyboard stinger: 1920x1080 @ 60fps, 1.5 s x SLOW, on #00FF00.

Renders a top-down mechanical keyboard that slides through the frame along a
10-degree diagonal, a red wave sweeping right-to-left while it covers the frame,
and a synthesized whoosh + key-click soundtrack.

Usage: python3 render_stinger.py <out_dir>
"""
import math
import os
import subprocess
import sys
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
FRAMES = os.path.join(OUT, "frames")
os.makedirs(FRAMES, exist_ok=True)

SLOW = 1.6                    # timing stretch vs. the original 1.5 s cut
W, H, FPS, DUR = 1920, 1080, 60, 1.5 * SLOW
NF = int(round(FPS * DUR))
THETA = math.radians(10.0)
SHUTTER = 0.75  # fraction of a frame the virtual shutter is open

def hexrgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255.0

GREEN = hexrgb("#00FF00")
KEYCAP = "#1A1A1D"
LEGEND = "#F5F5F5"
RED = hexrgb("#E8283C")

# ---------------------------------------------------------------- layout ----
U = 230                       # pixels per key unit at 1x
SS = 2                        # supersampling for the texture drawing
ML, MR, MT, MB = 0.55, 0.55, 0.55, 0.70   # case margins (units)
KW_U, KH_U = 22.5, 6.25
PAD = 420                     # transparent horizontal padding for motion blur
VPAD = 12

# (x, y, w, h, legend, kind)
keys = []
def row(y, x, items):
    for it in items:
        if it is None:
            x += 1
            continue
        if isinstance(it, (int, float)):
            x += it
            continue
        leg, w = it if isinstance(it, tuple) else (it, 1)
        keys.append([x, y, w, 1, leg, "std"])
        x += w

row(0, 0, ["⎋", 1, "F1", "F2", "F3", "F4", .5, "F5", "F6", "F7", "F8", .5,
           "F9", "F10", "F11", "F12", .25, "", "", ""])
row(1.25, 0, ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", ("⌫", 2),
              .25, "", "", "", .25, "", "/", "*", "-"])
row(2.25, 0, [("⇥", 1.5), "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", ("\\", 1.5),
              .25, "", "", "", .25, "7", "8", "9"])
row(3.25, 0, [("⇪", 1.75), "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", ("⏎", 2.25),
              3.5, "4", "5", "6"])
row(4.25, 0, [("⇧", 2.25), "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", ("⇧", 2.75),
              1.25, "↑", 1.25, "1", "2", "3"])
row(5.25, 0, [("⌃", 1.25), ("◆", 1.25), ("⌥", 1.25), ("", 6.25), ("⌥", 1.25), ("◆", 1.25),
              ("≡", 1.25), ("⌃", 1.25), .25, "←", "↓", "→", .25, ("0", 2), "."])
keys.append([21.5, 2.25, 1, 2, "+", "std"])
keys.append([21.5, 4.25, 1, 2, "⏎", "std"])

# The two brand keys sit at the centre of the home row (G and H positions).
for k in keys:
    if k[1] == 3.25 and k[4] == "G":
        k[4], k[5] = "Ctrl", "brand"
    elif k[1] == 3.25 and k[4] == "H":
        k[4], k[5] = "Bebo", "brand"

TW = int(round((KW_U + ML + MR) * U)) + 2 * PAD
TH = int(round((KH_U + MT + MB) * U)) + 2 * VPAD
OX, OY = PAD + ML * U, VPAD + MT * U       # texture px of layout origin

def kpx(x, y):
    return OX + x * U, OY + y * U

# anchor = boundary between Ctrl and Bebo, vertically on the home-row centre
ANCHOR = np.array(kpx(6.75, 3.75), np.float32)

# --------------------------------------------------------------- texture ----
def build_texture():
    s = SS
    base = Image.new("RGBA", (TW * s, TH * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    legend = Image.new("L", (TW * s, TH * s), 0)
    dl = ImageDraw.Draw(legend)
    face = Image.new("L", (TW * s, TH * s), 0)
    df = ImageDraw.Draw(face)
    skirt = Image.new("L", (TW * s, TH * s), 0)
    dsk = ImageDraw.Draw(skirt)

    # case + plate
    cx0, cy0 = PAD * s, VPAD * s
    cx1, cy1 = (TW - PAD) * s, (TH - VPAD) * s
    d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=int(.28 * U * s), fill=(10, 10, 12, 255))
    d.rounded_rectangle([cx0 + 3 * s, cy0 + 3 * s, cx1 - 3 * s, cy1 - 3 * s], radius=int(.26 * U * s),
                        outline=(30, 30, 34, 255), width=2 * s)
    px0, py0 = kpx(-.12, -.12)
    px1, py1 = kpx(KW_U + .12, KH_U + .12)
    d.rounded_rectangle([px0 * s, py0 * s, px1 * s, py1 * s], radius=int(.1 * U * s), fill=(13, 13, 15, 255))

    f_small = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Medium.otf", int(.135 * U * s))
    f_sym = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(.15 * U * s))
    f_brand = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", int(.27 * U * s))

    for x, y, w, h, leg, kind in keys:
        x0, y0 = kpx(x, y)
        x1, y1 = kpx(x + w, y + h)
        x0, y0, x1, y1 = (v * s for v in (x0, y0, x1, y1))
        g = .045 * U * s
        # skirt: dark base, lighter upper body -> reads as light from the top
        sk = [x0 + g, y0 + g, x1 - g, y1 - g]
        d.rounded_rectangle(sk, radius=int(.09 * U * s), fill=(14, 14, 16, 255))
        d.rounded_rectangle([sk[0], sk[1], sk[2], sk[3] - .05 * U * s], radius=int(.09 * U * s),
                            fill=(33, 33, 37, 255))
        dsk.rounded_rectangle(sk, radius=int(.09 * U * s), fill=255)
        # top face, slightly offset upward for subtle depth
        fc = [x0 + .14 * U * s, y0 + .095 * U * s, x1 - .14 * U * s, y1 - .2 * U * s]
        d.rounded_rectangle(fc, radius=int(.08 * U * s), fill=KEYCAP)
        d.rounded_rectangle(fc, radius=int(.08 * U * s), outline=(40, 40, 44, 255), width=max(1, int(1.5 * s)))
        df.rounded_rectangle(fc, radius=int(.08 * U * s), fill=255)
        if not leg:
            continue
        if kind == "brand":
            cx, cy = (fc[0] + fc[2]) / 2, (fc[1] + fc[3]) / 2
            dl.text((cx, cy), leg, font=f_brand, fill=255, anchor="mm")
        else:
            font = f_sym if not leg.isascii() else f_small
            dl.text((fc[0] + .07 * U * s, fc[1] + .06 * U * s), leg, font=font, fill=255, anchor="lt")

    def down(img):
        return np.asarray(img.resize((TW, TH), Image.LANCZOS), np.float32) / 255.0

    base = down(base)
    legend, face, skirt = down(legend), down(face), down(skirt)
    rgb = base[..., :3] * (1 - legend[..., None]) + hexrgb(LEGEND) * legend[..., None]
    alpha = base[..., 3]

    # light leaking from under each key onto the plate around it
    halo = cv2.GaussianBlur(skirt, (0, 0), .05 * U) * (1 - skirt) * 1.6
    halo = np.clip(halo, 0, 1) * alpha

    # key id map (cells), brand flags
    kid = np.zeros((TH, TW), np.int32)
    centers = []
    for i, (x, y, w, h, *_rest) in enumerate(keys, start=1):
        x0, y0 = kpx(x, y)
        x1, y1 = kpx(x + w, y + h)
        kid[int(y0):int(math.ceil(y1)), int(x0):int(math.ceil(x1))] = i
        centers.append(((x0 + x1) / 2, (y0 + y1) / 2))
    return rgb, alpha, legend, face, halo, kid, np.array(centers, np.float32)

print("building texture", TW, "x", TH)
TEX_RGB, TEX_A, LEG, FACE, HALO, KID, KCENT = build_texture()
IS_BRAND = np.array([0] + [k[5] == "brand" for k in keys], bool)
PREMULT = TEX_RGB * TEX_A[..., None]

# ---------------------------------------------------------------- motion ----
# s(t): along-axis offset of the Ctrl|Bebo anchor from frame centre.
# Fast slam in, slow glide while covering, fast zip out.
KEYS_T = [x * SLOW for x in (0.0, 0.5, 0.7, 0.9, 1.5)]
KEYS_S = [2950.0, 300.0, 0.0, -320.0, -5100.0]
KEYS_V = [v / SLOW for v in (-9500.0, -1700.0, -1500.0, -1800.0, -13500.0)]

def s_at(t):
    t = min(max(t, 0.0), DUR)
    for i in range(len(KEYS_T) - 1):
        if t <= KEYS_T[i + 1] + 1e-9:
            t0, t1 = KEYS_T[i], KEYS_T[i + 1]
            h = t1 - t0
            u = (t - t0) / h
            p0, p1, m0, m1 = KEYS_S[i], KEYS_S[i + 1], KEYS_V[i] * h, KEYS_V[i + 1] * h
            return ((2 * u**3 - 3 * u**2 + 1) * p0 + (u**3 - 2 * u**2 + u) * m0 +
                    (-2 * u**3 + 3 * u**2) * p1 + (u**3 - u**2) * m1)
    return KEYS_S[-1]

def v_at(t, dt=1e-4):
    return (s_at(t + dt) - s_at(t - dt)) / (2 * dt)

E = np.array([math.cos(THETA), math.sin(THETA)], np.float32)   # texture x on screen
N = np.array([-math.sin(THETA), math.cos(THETA)], np.float32)  # texture y on screen
C = np.array([W / 2, H / 2], np.float32)

def affine(t):
    b = C + (s_at(t) - ANCHOR[0]) * E - ANCHOR[1] * N
    return np.array([[E[0], N[0], b[0]], [E[1], N[1], b[1]]], np.float32)

def key_screen_x(t):
    M = affine(t)
    return KCENT[:, 0] * M[0, 0] + KCENT[:, 1] * M[0, 1] + M[0, 2]

# ------------------------------------------------------------------ wave ----
W_T0, W_T1, W_X0, W_X1 = 0.5 * SLOW, 0.86 * SLOW, 2150.0, -250.0

def wave_x(t):
    return W_X0 + (t - W_T0) / (W_T1 - W_T0) * (W_X1 - W_X0)

def smooth(a, b, x):
    x = np.clip((x - a) / (b - a), 0, 1)
    return x * x * (3 - 2 * x)

def hit_time(i):
    """time the wave front reaches key i (None if never)"""
    for t in np.arange(W_T0, W_T1 + 0.05 * SLOW, 0.001):
        if key_screen_x(t)[i] >= wave_x(t):
            return float(t)
    return None

T_HIT = np.array([hit_time(i) if hit_time(i) is not None else 9.0 for i in range(len(keys))], np.float32)

def key_intensity(t):
    xk = key_screen_x(t)
    d = xk - wave_x(t)
    ahead = np.exp(-(d / 120.0) ** 2)
    behind = np.exp(-np.maximum(d, 0) / 600.0)
    I = np.where(d < 0, ahead, behind)
    I *= (t > W_T0 - 0.02 * SLOW)
    I *= 1 - smooth(0.84 * SLOW, 0.98 * SLOW, t)
    brand = IS_BRAND[1:]
    lit = t >= T_HIT
    hold = lit * (1 - smooth(0.92 * SLOW, 1.12 * SLOW, t)) * (1 + 0.6 * np.exp(-((t - T_HIT) / (0.035 * SLOW)) ** 2))
    I = np.where(brand, np.maximum(I, hold), I)
    return np.concatenate([[0.0], I]).astype(np.float32)

GAIN = np.where(IS_BRAND, 1.0, 0.85).astype(np.float32)
FACE_TINT = np.where(IS_BRAND, 0.10, 0.06).astype(np.float32)
HALO_GAIN = np.where(IS_BRAND, 1.6, 0.85).astype(np.float32)

# ---------------------------------------------------------------- render ----
coverage = []
for f in range(NF):
    t = f / FPS
    I = key_intensity(t)
    if I.max() > 1e-3:
        Imap = I[KID]
        leg_lit = np.clip(LEG * Imap * GAIN[KID], 0, 1)
        glow_amt = (HALO * HALO_GAIN[KID] + FACE * FACE_TINT[KID]) * Imap
        glow = RED * np.clip(leg_lit + glow_amt, 0, 1)[..., None] * TEX_A[..., None]
        rgb = PREMULT * (1 - leg_lit[..., None]) + glow
        src = np.dstack([rgb, TEX_A])
        bloom_src = glow
    else:
        src = np.dstack([PREMULT, TEX_A])
        bloom_src = None

    v = abs(v_at(t))
    k = int(round(v / FPS * SHUTTER))
    if k > 1:
        src = cv2.blur(src, (k, 1), borderType=cv2.BORDER_CONSTANT)
        if bloom_src is not None:
            bloom_src = cv2.blur(bloom_src, (k, 1), borderType=cv2.BORDER_CONSTANT)

    M = affine(t)
    scr = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    a = np.clip(scr[..., 3:4], 0, 1)
    out = scr[..., :3] + GREEN * (1 - a)
    if bloom_src is not None:
        g = cv2.warpAffine(bloom_src, M, (W, H), flags=cv2.INTER_LINEAR)
        small = cv2.resize(g, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        b1 = cv2.GaussianBlur(small, (0, 0), 6)
        b2 = cv2.GaussianBlur(small, (0, 0), 18)
        bloom = cv2.resize(0.45 * b1 + 0.35 * b2, (W, H), interpolation=cv2.INTER_LINEAR)
        # keep bloom on the keyboard only so the key stays clean; never push past #E8283C
        out = np.minimum(out + bloom * a, np.maximum(out, RED))
    out = np.clip(out, 0, 1)
    green_px = int(((a[..., 0] < 0.999)).sum())
    coverage.append(green_px)
    cv2.imwrite(os.path.join(FRAMES, f"{f:04d}.png"),
                (out[..., ::-1] * 255 + 0.5).astype(np.uint8))
    print(f"frame {f:3d} t={t:.3f} v={v:7.0f} blur={k:3d} non-covered px={green_px}", flush=True)

# ----------------------------------------------------------------- audio ----
SR = 48000
NS = int(SR * DUR)
rng = np.random.default_rng(7)
L = np.zeros(NS); R = np.zeros(NS)

def pan_add(sig, start, pan):  # pan: -1 left .. +1 right, equal power
    i0 = int(start * SR)
    if i0 >= NS:
        return
    n = min(len(sig), NS - i0)
    ang = (pan + 1) * math.pi / 4
    L[i0:i0 + n] += sig[:n] * math.cos(ang)
    R[i0:i0 + n] += sig[:n] * math.sin(ang)

def click(loud=1.0, thock=0.4):
    n = int(0.06 * SR)
    tt = np.arange(n) / SR
    noise = rng.standard_normal(n)
    hp = np.diff(noise, prepend=0)
    tr = hp * np.exp(-tt / 0.0012) * 0.9
    f1, f2 = rng.uniform(2100, 2700), rng.uniform(3600, 4500)
    body = (np.sin(2 * np.pi * f1 * tt) + 0.6 * np.sin(2 * np.pi * f2 * tt)) * np.exp(-tt / 0.006) * 0.45
    lo = np.sin(2 * np.pi * rng.uniform(170, 260) * tt) * np.exp(-tt / 0.022) * thock
    sig = tr + body + lo
    # bottom-out: second softer transient 7-11 ms later
    off = int(rng.uniform(0.007, 0.011) * SR)
    sig[off:] += 0.55 * (tr[:n - off] + 0.6 * body[:n - off])
    return sig * loud

xs_hit = {}
for i, th in enumerate(T_HIT):
    if th > 2:
        continue
    x = key_screen_x(float(th))[i]
    if not (-50 <= x <= W + 50):
        continue
    is_b = keys[i][5] == "brand"
    loud = 1.0 if is_b else rng.uniform(0.35, 0.7)
    sig = click(loud, 0.9 if is_b else 0.35)
    pan_add(sig, th + rng.uniform(-0.004, 0.004), float(np.clip(x / W * 2 - 1, -1, 1)) * 0.8)

# whoosh: noise through a band-pass whose centre and level follow the speed
tt = np.arange(NS) / SR
speed = np.array([abs(v_at(t)) for t in tt[::48]])
speed = np.interp(tt, tt[::48], speed)
sp = speed / speed.max()
noise = rng.standard_normal(NS)
y = np.zeros(NS)
z1 = z2 = 0.0
for n_ in range(NS):  # state-variable filter, time varying cutoff
    fc = 220 + 2600 * sp[n_] ** 1.3
    fq = 2 * math.sin(math.pi * fc / SR)
    hp_ = noise[n_] - z2 - 0.9 * z1
    z1 += fq * hp_
    z2 += fq * z1
    y[n_] = z1
env = sp ** 1.6 * smooth(0.0, 0.05, tt) * (1 - smooth(DUR - 0.15, DUR, tt))
wh = y / np.abs(y).max() * env * 0.9
# pan follows the keyboard's along-axis centre
kb_center_x = np.array([W / 2 + (s_at(t) + (TW / 2 - ANCHOR[0])) * E[0] for t in tt[::48]])
pan = np.interp(tt, tt[::48], np.clip(kb_center_x / W * 2 - 1, -1, 1)) * 0.7
ang = (pan + 1) * np.pi / 4
L += wh * np.cos(ang); R += wh * np.sin(ang)

st = np.stack([L, R], 1)
st *= 10 ** (-1 / 20) / np.abs(st).max()
fade = np.ones(NS); fade[-240:] = np.linspace(1, 0, 240)
st *= fade[:, None]
with wave.open(os.path.join(OUT, "audio.wav"), "wb") as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes((st * 32767).astype("<i2").tobytes())

# ---------------------------------------------------------------- encode ----
mid = [coverage[f] for f in range(NF) if 0.5 * SLOW <= f / FPS <= 0.9 * SLOW]
print("max non-covered px during cover window:", max(mid))
print("first frame non-covered:", coverage[0], "last:", coverage[-1], "of", W * H)

subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(FRAMES, "%04d.png"),
                "-i", os.path.join(OUT, "audio.wav"), "-c:v", "libx264", "-preset", "slow", "-crf", "12",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart",
                os.path.join(OUT, "CtrlBebo_stinger_green_1080p60.mp4")], check=True)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(FRAMES, "%04d.png"),
                "-i", os.path.join(OUT, "audio.wav"), "-c:v", "prores_ks", "-profile:v", "3",
                "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le",
                os.path.join(OUT, "CtrlBebo_stinger_green_1080p60_ProRes.mov")], check=True)
print("done")
