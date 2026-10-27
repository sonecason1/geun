# -*- coding: utf-8 -*-
"""
전진 검증(모의투자) 기록기
==========================
매일 스크리너가 낸 '진입 신호 확인 / 패턴 형성 중' 결과를 그날 확정된 값(피벗·무효화·점수)으로 기록하고,
이후 실제 가격으로 진입·청산을 자동 추적한다. 과거 백테스트(bt/validate_models.py)와 같은 규칙을
'미리 고정'해서 쓰므로, 기록이 쌓이면 백테스트를 다시 끼워 맞추지 않고도 실제 성과를 확인할 수 있다.

규칙 (config.json "forward"에서 조절, 기본값 = 과거 검증과 동일)
- 기록: 상태가 진입 신호 확인 → 기록일 종가 진입
        상태가 패턴 형성 중 → 다음 5거래일 안에 [종가 > 피벗, 거래량 ≥ 직전 50일 평균 × 1.4,
        종가 ≤ 피벗 × 1.05]인 첫날 종가 진입. 그 전에 종가 < 무효화면 '미진입(무효화)',
        종가 > 피벗 × 1.05면 '미진입(추격 금지)', 5일이 지나면 '미진입(기간 만료)'
- 청산: 손절 = 무효화 × 0.99 (시가가 더 낮으면 시가), 종가 < 50일선이면 종가 청산, 최대 120거래일,
        왕복 비용 0.5%
- 참고값: 다음 날 시가(장 마감 후 신호를 보고 실제로 살 수 있는 가격)와 그 기준 수익률도 함께 기록
- 같은 종목·같은 모델이 감시 중이거나 보유 중이면 새로 기록하지 않음
- 거래량 0(거래정지)일은 계산에서 제외 (백테스트와 동일)

룩어헤드 방지: 기록 시점에 정해진 값(피벗·무효화·점수·시장 상태)은 이후 절대 바꾸지 않는다.
              이후 가격은 진입·성과 계산에만 쓴다. 성과는 매번 기록일부터 다시 계산하므로(멱등)
              같은 날 여러 번 실행해도 결과가 같다. 청산·미진입으로 끝난 기록은 고정한다.
"""
import json
import os

import numpy as np
import pandas as pd

WATCH, OPEN, CLOSED = "감시 중", "보유 중", "청산"
NO_INV, NO_CHASE, NO_EXP = "미진입(무효화)", "미진입(추격 금지)", "미진입(기간 만료)"
FINAL = (CLOSED, NO_INV, NO_CHASE, NO_EXP)
ACTIVE = (WATCH, OPEN)

DEFAULT = dict(enabled=True, window=5, vol_mult=1.4, vol_lookback=50, max_chase=0.05, stop_buffer=0.01,
               max_hold=120, cost=0.005, ma_exit=50)

# 과거 검증(2020-01~2026-09, 매매 1건 단위) 평균 R — 비교용 참고값. 전진 결과와 나란히 보여 주기만 한다
BACKTEST_REF = {"vcp": 0.11, "cup": 0.00, "c3": 0.02, "flat": 0.11, "power": -0.09}

LOG_FIELDS = ["id", "code", "name", "market", "model", "model_name", "log_date", "status0", "score",
              "pivot", "invalid", "close_at_log", "risk_at_log", "mkt_state", "mkt_strong"]
CALC_FIELDS = ["state", "entry_date", "entry", "stop", "risk", "next_open", "gap_next_open",
               "exit_date", "exit_price", "exit_reason", "hold", "ret", "R", "ret_open",
               "mfe20", "mae20", "fail20", "bench", "bench_ret", "excess", "last_date", "last_close"]


def _f(v, nd=4):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(v) else round(v, nd)


def market_state(bench_close, date):
    """KODEX 200 종가 > 50일선 > 200일선 여부. 기록일 '전일'까지의 값으로 판단(백테스트와 동일)"""
    if bench_close is None or len(bench_close) < 201:
        return "판단 불가", None
    s = bench_close[bench_close.index < pd.Timestamp(date)]
    if len(s) < 200:
        return "판단 불가", None
    c, m50, m200 = s.iloc[-1], s.iloc[-50:].mean(), s.iloc[-200:].mean()
    st = "상승 추세" if c > m50 > m200 else "하락 추세" if c < m50 < m200 else "혼조"
    return st, bool(c > m50 > m200)


def new_records(mstocks, existing, bench, cfg=None):
    """오늘 스크리너 결과에서 새 기록 생성. existing: 기존 기록 리스트"""
    from models import FORM, SIGNAL  # 지연 import (테스트에서 models 없이도 사용 가능하게)
    active = {(r["code"], r["model"]) for r in existing if r.get("state") in ACTIVE}
    ids = {r["id"] for r in existing}
    kospi = bench.get("KOSPI") if bench else None
    out = []
    for s in mstocks:
        date = s.get("asof")
        if not date:
            continue
        for e in s["models"]:
            if e["status"] not in (FORM, SIGNAL) or not e.get("pivot") or not e.get("invalid"):
                continue
            rid = f"{date}_{s['code']}_{e['model']}"
            if rid in ids or (s["code"], e["model"]) in active:
                continue
            mst, strong = market_state(kospi, date)
            close = s.get("close")
            stop = e["invalid"] * (1 - (cfg or DEFAULT)["stop_buffer"])
            out.append(dict(id=rid, code=s["code"], name=s["name"], market=s.get("market", "KOSPI"),
                            model=e["model"], model_name=e["model_name"], log_date=date, status0=e["status"],
                            score=e.get("score"), pivot=_f(e["pivot"], 2), invalid=_f(e["invalid"], 2),
                            close_at_log=_f(close, 2),
                            # 예상 손절폭: 진입 신호면 기록일 종가 기준, 패턴 형성 중이면 피벗(돌파 시 진입가) 기준
                            risk_at_log=_f(1 - stop / (close if e["status"] == SIGNAL else e["pivot"]))
                            if (close or e["pivot"]) else None,
                            mkt_state=mst, mkt_strong=strong, state=WATCH))
            active.add((s["code"], e["model"]))
    return out


def evaluate(rec, d, bench_close=None, cfg=None):
    """기록 1건을 가격 데이터 d(OHLCV, 날짜 인덱스, 기록일 이전 데이터 포함)로 다시 계산해 갱신한 사본을 반환"""
    cfg = {**DEFAULT, **(cfg or {})}
    r = {k: rec.get(k) for k in LOG_FIELDS}
    r.update({k: None for k in CALC_FIELDS})
    if d is None or len(d) == 0:
        r["state"] = rec.get("state") or WATCH
        return r
    d = d[d["Volume"] > 0]
    idx = d.index
    o, h, l, c, v = (d[k].values.astype(float) for k in ("Open", "High", "Low", "Close", "Volume"))
    ma = pd.Series(c).rolling(cfg["ma_exit"]).mean().values
    n = len(c)
    t = int(idx.searchsorted(pd.Timestamp(r["log_date"]), side="right")) - 1   # 기록일(또는 그 직전 거래일)
    if t < 0:
        r["state"] = WATCH
        return r
    r["last_date"], r["last_close"] = idx[-1].strftime("%Y-%m-%d"), _f(c[-1], 2)
    piv, inv = float(r["pivot"]), float(r["invalid"])

    # 1) 진입 찾기
    e, state = None, WATCH
    if r["status0"] != "패턴 형성 중":            # 진입 신호 확인 → 기록일 종가
        e = t
    else:
        lb = cfg["vol_lookback"]
        for j in range(t + 1, min(t + cfg["window"], n - 1) + 1):
            if c[j] < inv:
                state = NO_INV; break
            if c[j] > piv * (1 + cfg["max_chase"]):
                state = NO_CHASE; break
            if c[j] > piv and j >= lb and v[j] >= cfg["vol_mult"] * v[j - lb:j].mean():
                e = j; break
        else:
            if t + cfg["window"] <= n - 1:
                state = NO_EXP
    if e is None:
        r["state"] = state
        return r

    # 2) 진입 후 추적
    entry, stop = c[e], inv * (1 - cfg["stop_buffer"])
    risk = 1 - stop / entry
    r.update(entry_date=idx[e].strftime("%Y-%m-%d"), entry=_f(entry, 2), stop=_f(stop, 2), risk=_f(risk))
    if e + 1 < n:
        r["next_open"] = _f(o[e + 1], 2)
        r["gap_next_open"] = _f(o[e + 1] / entry - 1)
    w = slice(e + 1, min(e + 21, n))
    if e + 1 < n:
        r["mfe20"] = _f(h[w].max() / entry - 1)
        r["mae20"] = _f(l[w].min() / entry - 1)
        failed = bool((c[w] < inv).any())
        r["fail20"] = True if failed else (False if e + 20 <= n - 1 else None)   # 20일 안 지나면 미확정
    px, held, why = c[-1], n - 1 - e, None
    for k in range(e + 1, min(e + cfg["max_hold"] + 1, n)):
        if o[k] <= stop:
            px, held, why = o[k], k - e, "손절(시가 갭)"; break
        if l[k] <= stop:
            px, held, why = stop, k - e, "손절"; break
        if np.isfinite(ma[k]) and c[k] < ma[k]:
            px, held, why = c[k], k - e, f"{cfg['ma_exit']}일선 이탈"; break
    else:
        if e + cfg["max_hold"] <= n - 1:
            px, held, why = c[e + cfg["max_hold"]], cfg["max_hold"], "최대 보유"
    ret = px / entry * (1 - cfg["cost"]) - 1
    r.update(state=CLOSED if why else OPEN, hold=int(held), ret=_f(ret), R=_f(ret / risk) if risk > 0 else None)
    if why:
        r.update(exit_date=idx[e + held].strftime("%Y-%m-%d"), exit_price=_f(px, 2), exit_reason=why)
    if r["next_open"] and held >= 1:
        r["ret_open"] = _f(px / r["next_open"] * (1 - cfg["cost"]) - 1)
    # 3) 같은 기간 지수 (코스피=KODEX 200, 코스닥=KODEX 코스닥150)
    if bench_close is not None and len(bench_close):
        bi = bench_close.index
        a = bi.searchsorted(idx[e], side="right") - 1
        b = bi.searchsorted(idx[e + held], side="right") - 1
        if a >= 0 and b >= a:
            br = bench_close.iloc[b] / bench_close.iloc[a] - 1
            r.update(bench_ret=_f(br), excess=_f(ret - br))
    return r


def summarize(records):
    df = pd.DataFrame(records)
    df = df.reindex(columns=sorted(set(df.columns) | set(LOG_FIELDS) | set(CALC_FIELDS)))
    out = dict(total=len(df))
    if df.empty:
        out.update(by_state={}, by_model=[], by_market=[])
        return out
    out["by_state"] = df["state"].value_counts().to_dict()
    rows = []
    for mk, g in df.groupby("model"):
        cl = g[g["state"] == CLOSED]
        traded = g[g["entry_date"].notna()]
        rows.append(dict(model=mk, model_name=g["model_name"].iloc[0], logged=len(g),
                         watch=int((g["state"] == WATCH).sum()), open=int((g["state"] == OPEN).sum()),
                         closed=len(cl), no_entry=int(g["state"].isin([NO_INV, NO_CHASE, NO_EXP]).sum()),
                         entry_rate=_f(len(traded) / len(g)) if len(g) else None,
                         win=_f((cl["ret"] > 0).mean()) if len(cl) else None,
                         avg_R=_f(cl["R"].mean()) if len(cl) else None,
                         med_R=_f(cl["R"].median()) if len(cl) else None,
                         avg_ret=_f(cl["ret"].mean()) if len(cl) else None,
                         avg_ret_open=_f(cl["ret_open"].mean()) if len(cl) and cl["ret_open"].notna().any() else None,
                         avg_excess=_f(cl["excess"].mean()) if len(cl) and cl["excess"].notna().any() else None,
                         backtest_R=BACKTEST_REF.get(mk)))
    out["by_model"] = rows
    mk_rows = []
    for k, g in df[df["state"] == CLOSED].groupby(df["mkt_strong"].map({True: "강한 시장", False: "약한·혼조 시장"})
                                                  .fillna("판단 불가")):
        mk_rows.append(dict(market=k, closed=len(g), win=_f((g["ret"] > 0).mean()), avg_R=_f(g["R"].mean())))
    out["by_market"] = mk_rows
    return out


# ───────────────────────── 파일 입출력 (run_tv.py에서 호출) ─────────────────────────
def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("records", [])


def update(path_dir, mstocks, hist, bench, fetch, start, cfg=None, today=None):
    """기록 추가 + 미완료 기록 재계산 + 저장. fetch(code, start) -> (code, df). 반환: 감시·보유 중 종목 코드 집합"""
    cfg = {**DEFAULT, **(cfg or {})}
    os.makedirs(path_dir, exist_ok=True)
    jpath = os.path.join(path_dir, "ledger.json")
    recs = load(jpath)
    recs += new_records(mstocks, recs, bench, cfg)
    need = sorted({r["code"] for r in recs if r.get("state") not in FINAL} - set(hist))
    extra = dict(fetch(cd, start) for cd in need)
    bmap = {"KOSPI": bench.get("KOSPI"), "KOSDAQ": bench.get("KOSDAQ", bench.get("KOSPI"))}
    out = []
    for r in recs:
        if r.get("state") in FINAL:
            out.append(r); continue
        d = hist.get(r["code"])
        if d is None:
            d = extra.get(r["code"])
        if d is None:                                     # 데이터 조회 실패 → 이전 값 유지
            out.append({**r, "note": "가격 조회 실패(이번 실행)"}); continue
        nr = evaluate(r, d, bmap.get(r.get("market"), bmap["KOSPI"]), cfg)
        nr["bench"] = "KODEX 코스닥150" if r.get("market") == "KOSDAQ" else "KODEX 200"
        out.append(nr)
    out.sort(key=lambda x: (x["log_date"], x["code"], x["model"]))
    summ = summarize(out)
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(dict(updated=today, rules=cfg, backtest_ref=BACKTEST_REF, summary=summ, records=out),
                  f, ensure_ascii=False, separators=(",", ":"))
    cols = {"log_date": "기록일", "code": "종목코드", "name": "종목명", "market": "시장", "model_name": "모델",
            "status0": "기록 시 상태", "score": "점수", "pivot": "피벗", "invalid": "무효화", "close_at_log": "기록일 종가",
            "risk_at_log": "예상 손절폭", "mkt_state": "시장 상태", "state": "현재 상태", "entry_date": "진입일",
            "entry": "진입가(종가)", "next_open": "다음날 시가", "gap_next_open": "시가 괴리", "stop": "손절가",
            "risk": "손절폭", "exit_date": "청산일", "exit_price": "청산가", "exit_reason": "청산 사유", "hold": "보유일",
            "ret": "수익률", "R": "R", "ret_open": "수익률(다음날 시가 진입)", "mfe20": "20일 최대상승",
            "mae20": "20일 최대역행", "fail20": "20일 실패", "bench": "비교 지수", "bench_ret": "지수 수익률",
            "excess": "지수 대비", "last_date": "최종 데이터일", "last_close": "최종 종가"}
    pd.DataFrame(out).reindex(columns=list(cols)).rename(columns=cols).to_csv(
        os.path.join(path_dir, "ledger.csv"), index=False, encoding="utf-8-sig")
    return {r["code"] for r in out if r.get("state") in ACTIVE}, summ
