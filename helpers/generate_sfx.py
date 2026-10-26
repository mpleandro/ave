"""Synthesize a small royalty-free SFX pack (no external files/licensing).
Run: uv run python generate.py   → whoosh.wav, pop.wav, click.wav (then mp3)
"""
import numpy as np, wave, struct
SR = 44100

def save(name, y):
    y = y / (np.max(np.abs(y)) + 1e-9)
    y = np.tanh(y * 1.1)                       # soft clip
    pcm = (y * 0.85 * 32767).astype(np.int16)
    with wave.open(name, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", name, f"{len(y)/SR:.2f}s")

def onepole_sweep(x, a):                         # time-varying one-pole lowpass
    y = np.empty_like(x); prev = 0.0
    for i in range(len(x)):
        prev += a[i] * (x[i] - prev); y[i] = prev
    return y

# WHOOSH — filtered noise, cutoff opens then closes, smooth amplitude hump
n = int(0.45 * SR); t = np.linspace(0, 1, n)
noise = np.random.randn(n)
a = 0.02 + 0.38 * np.sin(np.pi * t) ** 1.2       # cutoff low→high→low
whoosh = onepole_sweep(noise, a)
env = np.sin(np.pi * t) ** 1.4
save("whoosh.wav", whoosh * env)

# POP — short tonal blip with a pitch drop + tiny transient
n = int(0.14 * SR); t = np.linspace(0, 0.14, n)
f = 680 * np.exp(-t * 7)                          # 680→~250 Hz
tone = np.sin(2 * np.pi * np.cumsum(f) / SR)
trans = np.random.randn(n) * np.exp(-t * 120) * 0.4
pop = (tone + trans) * np.exp(-t * 26)
save("pop.wav", pop)

# CLICK — very short transient
n = int(0.03 * SR); t = np.linspace(0, 0.03, n)
click = np.random.randn(n) * np.exp(-t * 260)
save("click.wav", click)

# CA-CHING — caixa registradora: o "ca" é o trinco (dois cliques secos de
# ruído com corpo grave), o "ching" é um sino de parciais INARMÔNICOS (é o que
# faz soar metal e não nota musical), com um tremolo leve de moeda.
def caching():
    dur = 0.95
    n = int(dur * SR); t = np.arange(n) / SR
    y = np.zeros(n)
    for t0, g in ((0.0, 1.0), (0.045, 0.7)):          # ca-ca: trinco mecânico
        i0 = int(t0 * SR); m = int(0.035 * SR); tt = np.arange(m) / SR
        clk = (np.random.randn(m) * 0.6 + np.sin(2 * np.pi * 180 * tt)) * np.exp(-tt * 140)
        y[i0:i0 + m] += g * 0.8 * clk
    tb = np.clip(t - 0.085, 0, None); on = (t >= 0.085).astype(float)
    sino = sum(a * np.sin(2 * np.pi * f * tb) * np.exp(-tb * d)
               for f, a, d in ((2093, 1.0, 4.2), (2637, 0.8, 4.8), (3520, 0.55, 6.0),
                               (4699, 0.4, 7.5), (6272, 0.25, 9.0), (2349, 0.35, 5.0)))
    sino *= 1 + 0.18 * np.sin(2 * np.pi * 11 * tb)    # tremolo de moeda
    y += on * sino * 0.75
    return y


save("caching.wav", caching())
