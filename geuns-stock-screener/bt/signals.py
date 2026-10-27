# -*- coding: utf-8 -*-
"""1단계: 날짜별 트렌드 템플릿 + RS + 유동성 → VCP 탐지 → 신호(피벗·손절가) 저장
   look-ahead 방지: t일 신호는 t일 종가까지의 데이터만 사용, 주문은 t+1일부터"""
import os as _os
HERE=_os.path.dirname(_os.path.abspath(__file__))
import pickle, sys, time, warnings
from multiprocessing import Pool
import numpy as np
import pandas as pd

sys.path.insert(0, _os.path.join(HERE,"..","screener"))
from vcp import detect_vcp  # 사이트 스크리너와 같은 VCP 로직

warnings.filterwarnings("ignore")
SIG_START = pd.Timestamp("2019-12-01")
DB = pickle.load(open(_os.path.join(HERE,"prices.pkl"), "rb"))
PR = DB["prices"]
dates = DB["bench"].index

# RS 백분위 (전 종목 단면 순위, IBD 방식: 3개월 2배 가중)
C = pd.DataFrame({c: d["Close"] for c, d in PR.items()}).reindex(dates).astype("float32")
Cf = C.ffill(limit=5)
raw = (2 * Cf / Cf.shift(63) + Cf / Cf.shift(126) + Cf / Cf.shift(189) + Cf / Cf.shift(252)) / 5
RS = (raw.rank(axis=1, pct=True) * 98 + 1).astype("float32")
del raw, Cf


def cand_mask(d, rs):
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    m50, m150, m200 = c.rolling(50).mean(), c.rolling(150).mean(), c.rolling(200).mean()
    hi52, lo52 = h.rolling(252, min_periods=200).max(), l.rolling(252, min_periods=200).min()
    tt = ((c > m150) & (c > m200) & (m150 > m200) & (m200 > m200.shift(21)) & (m50 > m150) &
          (m50 > m200) & (c > m50) & (c >= lo52 * 1.3) & (c >= hi52 * 0.75))
    turn = (c * v).rolling(20).mean()
    return tt & (rs >= 70) & (turn >= 30e8) & (d.index >= SIG_START)


def run(code):
    d = PR[code]
    rs = RS[code].reindex(d.index)
    m = cand_mask(d, rs).values
    out = []
    for i in np.where(m)[0]:
        if i < 150:
            continue
        v = detect_vcp(d.iloc[i - 140:i + 1])
        if v.get("VCP") and v.get("피벗거리", 1) <= 0:
            out.append((d.index[i], code, float(v["피벗"]), float(v["손절가"]), float(rs.iloc[i]),
                        len(v["수축"]), float(v["수축"][-1]), float(v.get("거래량수축비", np.nan))))
    return code, int(m.sum()), out


if __name__ == "__main__":
    t0 = time.time()
    codes = list(PR)
    if len(sys.argv) > 1:
        codes = codes[:int(sys.argv[1])]
    sigs, ncand = [], 0
    with Pool(2) as p:
        for i, (c, n, o) in enumerate(p.imap_unordered(run, codes, chunksize=20), 1):
            ncand += n
            sigs += o
            if i % 500 == 0:
                print(i, ncand, len(sigs), f"{time.time()-t0:.0f}s", flush=True)
    df = pd.DataFrame(sigs, columns=["date", "code", "pivot", "stop", "rs", "n_contr", "last_contr", "vol_dry"])
    df.to_pickle(_os.path.join(HERE,"signals.pkl"))
    RS.to_pickle(_os.path.join(HERE,"rs.pkl"))
    print("후보일", ncand, "신호", len(df), "종목", df["code"].nunique(), f"{time.time()-t0:.0f}s")
