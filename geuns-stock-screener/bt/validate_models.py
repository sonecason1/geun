# -*- coding: utf-8 -*-
"""
진입모델 워크포워드 검증 (파라미터 최적화 없음 - config.json 초기값 그대로)
=========================================================================
1) 2020-01 ~ 2026-09, 5거래일마다 기준일 t를 잡고, 사이트와 같은 넓은 사전 필터를 통과한 종목에
   models.analyze_stock(그날까지 약 345봉, recent=False)을 실행 → '패턴 형성 중/진입 신호' 기록
2) 진입: t일 신호면 t일 종가. 형성 중이면 t+1 ~ t+5일 중 [종가 > 피벗, 거래량 ≥ 직전 50일 평균 1.4배,
   종가 ≤ 피벗 +5%]인 첫날 종가. 그 전에 종가가 무효화 가격 아래면 취소. (피벗·무효화는 t일에 확정된 값)
3) 성과 (모든 모델 동일 규칙, 고정):
   - MFE/MAE: 진입 후 20·60거래일 최대 상승폭(고가)·최대 역행폭(저가)
   - 실패: 20거래일 안에 종가가 무효화 가격 아래
   - 매매 결과: 손절 = 무효화 가격 ×0.99 (시가가 더 낮으면 시가), 종가 50일선 이탈 시 청산, 최대 120거래일,
     비용 왕복 0.5%
4) 비교 기준: 기존 VCP 스크리너 신호(signals.pkl)를 같은 기준일·같은 진입/청산 규칙으로 처리
룩어헤드: 기준일 판정은 t일까지의 데이터만, 이후 데이터는 진입·성과 측정에만 사용
"""
import os as _os
HERE=_os.path.dirname(_os.path.abspath(__file__))
import pickle
import sys
import time
import warnings
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, _os.path.join(HERE,"..","screener"))
import models as M  # noqa: E402

CFG = M.load_config()
DB = pickle.load(open(_os.path.join(HERE,"prices.pkl"), "rb"))
PR, UNI = DB["prices"], DB["uni"]
BENCH = DB["bench"]["Close"].astype(float)
NAME = dict(zip(UNI["Code"], UNI["Name"]))
DATES = BENCH.index
SAMPLES = DATES[(DATES >= "2020-01-02") & (DATES <= "2026-09-30")][::5]
WIN, BARS, COST = 5, 345, 0.005
_b50, _b200 = BENCH.rolling(50).mean(), BENCH.rolling(200).mean()
MKT_STRONG = ((BENCH > _b50) & (_b50 > _b200)).shift(1).fillna(False).astype(bool)


def prefilter(d):
    """사이트 run_tv.py model_prefilter와 같은 조건 (TradingView 값 대신 일봉으로 계산)"""
    p, u = CFG["prefilter"], CFG["universe"]
    c, v = d["Close"], d["Volume"]
    ma200 = c.rolling(200).mean()
    hi52 = d["High"].rolling(252, min_periods=60).max()
    turn = (c * v).rolling(u["turnover_days"]).mean()
    perf3m = c / c.shift(63) - 1
    near = (ma200.isna() | (c >= ma200 * p["min_close_to_ma200"])) & (c >= hi52 * p["min_from_52w_high"])
    return (turn >= u["min_turnover"]) & (near | (perf3m * 100 >= p["power_perf3m_min"]))


def find_entry(a, t, piv, inv, signal_today):
    o, c, v = a["o"], a["c"], a["v"]
    if signal_today:
        return t
    for j in range(t + 1, min(t + WIN, len(c) - 1) + 1):
        if c[j] < inv:
            return None
        if c[j] > piv * 1.05:
            return None
        if c[j] > piv and j >= 50 and v[j] >= 1.4 * v[j - 50:j].mean():
            return j
    return None


def outcome(a, e, inv):
    o, h, l, c, ma50 = a["o"], a["h"], a["l"], a["c"], a["ma50"]
    n, entry = len(c), c[e]
    stop = inv * 0.99
    out = dict(entry=float(entry), stop=float(stop), risk=float(1 - stop / entry))
    for k in (20, 60):
        w = slice(e + 1, min(e + 1 + k, n))
        out[f"mfe{k}"] = float(h[w].max() / entry - 1) if e + 1 < n else np.nan
        out[f"mae{k}"] = float(l[w].min() / entry - 1) if e + 1 < n else np.nan
        out[f"full{k}"] = e + k < n
    w20 = c[e + 1:min(e + 21, n)]
    out["fail20"] = bool((w20 < inv).any()) if len(w20) else np.nan
    px, held, done = c[-1], n - 1 - e, False
    for t in range(e + 1, min(e + 121, n)):
        if o[t] <= stop:
            px, held, done = o[t], t - e, True; break
        if l[t] <= stop:
            px, held, done = stop, t - e, True; break
        if np.isfinite(ma50[t]) and c[t] < ma50[t]:
            px, held, done = c[t], t - e, True; break
    else:
        if e + 120 < n:
            px, held, done = c[e + 120], 120, True
    ret = px / entry * (1 - COST) - 1
    out.update(ret=float(ret), R=float(ret / out["risk"]) if out["risk"] > 0 else np.nan, hold=held, closed=done)
    return out


def arrays(d):
    c = d["Close"].values.astype(float)
    return dict(o=d["Open"].values.astype(float), h=d["High"].values.astype(float), l=d["Low"].values.astype(float),
                c=c, v=d["Volume"].values.astype(float), ma50=pd.Series(c).rolling(50).mean().values)


def run_stock(code):
    d = PR[code].astype(float)
    if len(d) < 300:
        return code, [], 0
    a = arrays(d)
    pos = {t: i for i, t in enumerate(d.index)}
    pf = prefilter(d).values
    rows, ncall, last = [], 0, {}
    for s in SAMPLES:
        t = pos.get(s)
        if t is None or t < 80 or not pf[t]:
            continue
        res = M.analyze_stock(d.iloc[max(0, t - BARS + 1):t + 1], BENCH, CFG, recent=False)
        ncall += 1
        for e_ in res["models"]:
            if e_["status"] not in (M.FORM, M.SIGNAL) or not e_.get("pivot") or not e_.get("invalid"):
                continue
            mk = e_["model"]
            ei = find_entry(a, t, e_["pivot"], e_["invalid"], e_["status"] == M.SIGNAL)
            if ei is None or last.get(mk, -1) >= ei:          # 같은 모델 중복 진입 방지(보유 중 재신호 무시)
                continue
            oc = outcome(a, ei, e_["invalid"])
            last[mk] = ei + oc["hold"]
            rows.append(dict(code=code, name=NAME.get(code, ""), model=mk, sample=s, entry_date=d.index[ei],
                             score=e_["score"], status0=e_["status"], pivot=e_["pivot"], invalid=e_["invalid"],
                             mkt_strong=bool(MKT_STRONG.get(d.index[ei], False)),
                             **{f"c_{k}": v for k, v in (e_.get("components") or {}).items()}, **oc))
    return code, rows, ncall


def run_legacy():
    """기존 VCP 신호(signals.pkl: 기존 detect_vcp, 트렌드 템플릿+RS70+거래대금) → 같은 기준일·같은 규칙"""
    sig = pd.read_pickle(_os.path.join(HERE,"signals.pkl"))
    sig = sig[sig["date"].isin(set(SAMPLES))]
    rows, last = [], {}
    for code, g in sig.groupby("code"):
        d = PR[code].astype(float)
        a = arrays(d)
        pos = {t: i for i, t in enumerate(d.index)}
        for _, r in g.sort_values("date").iterrows():
            t = pos[r["date"]]
            ei = find_entry(a, t, r["pivot"], r["stop"], False)
            if ei is None or last.get(code, -1) >= ei:
                continue
            oc = outcome(a, ei, r["stop"])
            last[code] = ei + oc["hold"]
            rows.append(dict(code=code, name=NAME.get(code, ""), model="legacy_vcp", sample=r["date"],
                             entry_date=d.index[ei], score=np.nan, mkt_strong=bool(MKT_STRONG.get(d.index[ei], False)),
                             pivot=r["pivot"], invalid=r["stop"], **oc))
    return rows


if __name__ == "__main__":
    t0 = time.time()
    codes = list(PR) if len(sys.argv) < 2 else list(PR)[:int(sys.argv[1])]
    allrows, calls = [], 0
    with Pool(2) as p:
        for i, (c, r, n) in enumerate(p.imap_unordered(run_stock, codes, chunksize=10), 1):
            allrows += r
            calls += n
            if i % 400 == 0:
                print(i, calls, len(allrows), f"{time.time() - t0:.0f}s", flush=True)
    leg = run_legacy()
    df = pd.DataFrame(allrows + leg)
    df.to_pickle(_os.path.join(HERE,"model_trades.pkl"))
    print("판정 호출", calls, "진입", len(df), f"{time.time() - t0:.0f}s")
