# -*- coding: utf-8 -*-
"""테스트용 가상 일봉 생성기 (교육용 차트 make_patterns.py의 생성 로직과 같은 방식)"""
import numpy as np
import pandas as pd


def interp(wp, n):
    ts = np.array([w[0] for w in wp], float); vs = np.array([w[1] for w in wp], float)
    out = np.empty(n)
    for t in range(n):
        if t <= ts[0]: out[t] = vs[0]
        elif t >= ts[-1]: out[t] = vs[-1]
        else:
            i = np.searchsorted(ts, t, side="right") - 1
            mu = (t - ts[i]) / (ts[i + 1] - ts[i]); m2 = (1 - np.cos(mu * np.pi)) / 2
            out[t] = vs[i] * (1 - m2) + vs[i + 1] * m2
    return out


def gen(wp, volwp, vwp, n, seed, updn=(1.15, 0.85), scale=10000):
    rng = np.random.default_rng(seed)
    base = interp(wp, n); sig = np.interp(np.arange(n), *zip(*volwp))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.45 * e[t - 1] + rng.normal(0, sig[t] * 0.65)
    c = base * (1 + e)
    o = np.r_[c[0], c[:-1] * (1 + rng.normal(0, sig[1:] * 0.3))]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, sig * 0.55)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, sig * 0.55)))
    vb = np.interp(np.arange(n), *zip(*vwp))
    v = vb * np.exp(rng.normal(0, 0.22, n)) * np.where(c >= o, updn[0], updn[1])
    return dict(o=o * scale / 100, h=h * scale / 100, l=l * scale / 100, c=c * scale / 100, v=v * 1e6)


def set_bar(d, t, o, c, hi=None, lo=None, vmult=None):
    d["o"][t], d["c"][t] = o, c
    d["h"][t] = hi if hi else max(o, c) * 1.006
    d["l"][t] = lo if lo else min(o, c) * 0.994
    if vmult:
        d["v"][t] = vmult * d["v"][t - 50:t].mean()


def to_df(d):
    n = len(d["c"])
    idx = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame({"Open": d["o"], "High": d["h"], "Low": d["l"], "Close": d["c"], "Volume": d["v"]}, index=idx)


def bench_for(df, drift=0.0003):
    return pd.Series(100 * (1 + drift) ** np.arange(len(df)), index=df.index)


def _breakout(d, tb, pivot_lo, pivot_hi, mult=2.3, up=1.035):
    piv = d["h"][pivot_lo:pivot_hi].max()
    set_bar(d, tb, d["c"][tb - 1] * 1.003, piv * up, hi=piv * (up + 0.006), vmult=mult)
    return piv


def vcp(mult=2.4):
    n = 372
    wp = [(0, 40), (60, 42), (110, 40), (150, 45), (225, 80), (245, 60), (270, 77), (285, 67), (300, 75.5),
          (310, 70.2), (322, 74.8), (330, 72.4), (338, 74.0), (339, 74.1), (371, 92)]
    volwp = [(0, .016), (225, .017), (240, .02), (270, .014), (290, .011), (305, .008), (322, .006), (330, .0035),
             (339, .003), (341, .014), (371, .014)]
    vwp = [(0, 1.0), (150, 1.0), (200, 1.6), (225, 1.7), (245, 1.5), (270, 1.0), (290, .8), (310, .6), (325, .45),
           (339, .35), (341, 1.4), (371, 1.1)]
    d = gen(wp, volwp, vwp, n, seed=7); tb = 340
    piv = d["h"][318:tb].max()
    set_bar(d, tb, piv * 0.997, piv * 1.04, hi=piv * 1.047, vmult=mult)
    return to_df(d), tb


def cup():
    n, L = 360, 240
    wp = [(0, 50), (90, 52), (140, 55), (L, 100), (L + 12, 86), (L + 25, 74), (L + 35, 70.5), (L + 46, 73.5),
          (L + 58, 86), (L + 70, 97.5), (L + 76, 93), (L + 82, 90), (L + 87, 92.5), (L + 88, 92.7), (n - 1, 112)]
    volwp = [(0, .015), (L, .016), (L + 15, .02), (L + 35, .013), (L + 60, .013), (L + 72, .009), (L + 87, .004),
             (L + 90, .013), (n - 1, .013)]
    vwp = [(0, 1.0), (180, 1.3), (L, 1.5), (L + 12, 1.7), (L + 30, .9), (L + 40, .7), (L + 60, 1.1), (L + 70, 1.0),
           (L + 78, .55), (L + 88, .4), (L + 90, 1.4), (n - 1, 1.1)]
    d = gen(wp, volwp, vwp, n, seed=11); tb = L + 89
    _breakout(d, tb, L + 66, L + 74)
    return to_df(d), tb


def cheat():
    n, L = 345, 240
    wp = [(0, 50), (90, 52), (140, 55), (L, 100), (L + 12, 86), (L + 25, 74), (L + 34, 70.5), (L + 42, 74),
          (L + 50, 82.5), (L + 53, 81), (L + 56, 82.3), (L + 59, 81.2), (L + 61, 82), (L + 62, 82.1),
          (L + 80, 95), (L + 90, 99), (n - 1, 106)]
    volwp = [(0, .015), (L, .016), (L + 15, .02), (L + 34, .013), (L + 50, .012), (L + 52, .004), (L + 62, .003),
             (L + 64, .013), (n - 1, .013)]
    vwp = [(0, 1.0), (180, 1.3), (L, 1.5), (L + 12, 1.7), (L + 30, .9), (L + 40, .8), (L + 50, 1.1), (L + 53, .5),
           (L + 62, .38), (L + 64, 1.3), (n - 1, 1.0)]
    d = gen(wp, volwp, vwp, n, seed=5); tb = L + 63
    _breakout(d, tb, L + 49, tb, mult=2.0, up=1.03)
    return to_df(d), tb


def flat():
    n, P = 345, 280
    wp = [(0, 40), (100, 42), (150, 45), (200, 55), (215, 52), (230, 54), (240, 58), (P, 86), (P + 7, 79.5),
          (P + 13, 84.5), (P + 19, 77.5), (P + 26, 85), (P + 32, 81.5), (P + 38, 85.2), (P + 41, 84.2),
          (P + 42, 84.4), (n - 1, 98)]
    volwp = [(0, .015), (P, .016), (P + 8, .012), (P + 20, .010), (P + 32, .007), (P + 42, .0035), (P + 44, .013),
             (n - 1, .013)]
    vwp = [(0, 1.0), (240, 1.8), (P, 1.6), (P + 10, 1.0), (P + 25, .7), (P + 38, .5), (P + 42, .4), (P + 44, 1.4),
           (n - 1, 1.1)]
    d = gen(wp, volwp, vwp, n, seed=21); tb = P + 43
    _breakout(d, tb, P - 3, tb, mult=2.2)
    return to_df(d), tb


def power():
    n, S = 320, 240
    wp = [(0, 21), (100, 20), (180, 21.5), (S, 20.5), (S + 8, 26), (S + 20, 34), (S + 36, 43), (S + 42, 37.5),
          (S + 48, 41.5), (S + 54, 38.5), (S + 59, 41.8), (S + 62, 40.8), (S + 63, 41), (n - 1, 52)]
    volwp = [(0, .015), (S, .014), (S + 2, .03), (S + 36, .028), (S + 42, .018), (S + 50, .011), (S + 58, .007),
             (S + 63, .004), (S + 65, .02), (n - 1, .02)]
    vwp = [(0, 1.0), (S, 0.9), (S + 2, 4), (S + 20, 3.2), (S + 36, 2.8), (S + 42, 1.3), (S + 52, .8), (S + 63, .5),
           (S + 65, 2), (n - 1, 1.5)]
    d = gen(wp, volwp, vwp, n, seed=3)
    set_bar(d, S + 1, d["c"][S] * 1.0, d["c"][S] * 1.15, vmult=6.5)
    tb = S + 64
    _breakout(d, tb, S + 30, tb, mult=1.8, up=1.04)
    return to_df(d), tb


def downtrend():
    n = 330
    wp = [(0, 100), (60, 110), (120, 92), (180, 75), (230, 60), (250, 52), (268, 58), (280, 54), (292, 57.5),
          (302, 55.5), (312, 57.2), (329, 56.5)]
    d = gen(wp, [(0, .016), (250, .016), (300, .008), (329, .006)], [(0, 1.2), (250, 1.4), (329, .7)], n, seed=12)
    return to_df(d)


def loose():
    n = 330
    wp = [(0, 40), (150, 44), (225, 80), (242, 56), (262, 77), (280, 55.5), (298, 75), (314, 56), (329, 70)]
    d = gen(wp, [(0, .018), (329, .03)], [(0, 1), (225, 1.6), (329, 1.2)], n, seed=4)
    return to_df(d)
