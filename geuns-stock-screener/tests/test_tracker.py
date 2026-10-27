# -*- coding: utf-8 -*-
"""전진 검증 기록기 테스트: python -m pytest tests -q"""
import os
import sys

import numpy as np
import pandas as pd

sys.path[:0] = [os.path.join(os.path.dirname(__file__), "..", "screener")]
import tracker as T  # noqa: E402

CFG = dict(T.DEFAULT)


def frame(closes, vols=None, opens=None, highs=None, lows=None, start="2026-01-01"):
    c = np.asarray(closes, float)
    idx = pd.bdate_range(start, periods=len(c))
    o = np.asarray(opens, float) if opens is not None else c.copy()
    h = np.asarray(highs, float) if highs is not None else np.maximum(o, c) * 1.005
    lo = np.asarray(lows, float) if lows is not None else np.minimum(o, c) * 0.995
    v = np.asarray(vols, float) if vols is not None else np.full(len(c), 1000.0)
    return pd.DataFrame(dict(Open=o, High=h, Low=lo, Close=c, Volume=v), index=idx)


def rec(d, t, status="패턴 형성 중", pivot=100.0, invalid=92.0, market="KOSPI"):
    return dict(id="x", code="000001", name="테스트", market=market, model="vcp", model_name="VCP",
                log_date=d.index[t].strftime("%Y-%m-%d"), status0=status, score=70, pivot=pivot, invalid=invalid,
                close_at_log=float(d["Close"].iloc[t]), risk_at_log=None, mkt_state="혼조", mkt_strong=False,
                state=T.WATCH)


def base(n=80, level=98.0):
    """완만한 상승으로 50일선 아래로 떨어지지 않는 기본 구간"""
    return list(np.linspace(80, level, n))


def test_breakout_entry_needs_volume_and_closes_above_pivot():
    cl = base() + [99, 101, 102]                      # t=79 기록, t+1=99(미돌파), t+2=101 거래량 부족, t+3 거래량 동반
    v = [1000] * 80 + [1000, 1100, 2000]
    d = frame(cl, v)
    r = T.evaluate(rec(d, 79), d, cfg=CFG)
    assert r["entry_date"] == d.index[82].strftime("%Y-%m-%d") and r["entry"] == 102
    assert r["state"] == T.OPEN and r["stop"] == round(92 * 0.99, 2)


def test_no_lookahead_future_rows_do_not_change_past_entry():
    cl = base() + [101, 103, 104, 106, 107]
    v = [1000] * 80 + [2000, 1000, 1000, 1000, 1000]
    d = frame(cl, v)
    r_short = T.evaluate(rec(d, 79), d.iloc[:82], cfg=CFG)
    r_long = T.evaluate(rec(d, 79), d, cfg=CFG)
    assert r_short["entry_date"] == r_long["entry_date"] == d.index[80].strftime("%Y-%m-%d")
    assert r_short["entry"] == r_long["entry"] == 101


def test_invalidation_before_breakout():
    cl = base() + [95, 91, 101]
    v = [1000] * 80 + [1000, 1000, 3000]
    d = frame(cl, v)
    assert T.evaluate(rec(d, 79), d, cfg=CFG)["state"] == T.NO_INV


def test_chase_limit():
    cl = base() + [106]
    d = frame(cl, [1000] * 80 + [5000])
    assert T.evaluate(rec(d, 79), d, cfg=CFG)["state"] == T.NO_CHASE


def test_window_expiry_and_pending():
    cl = base() + [99, 99.5, 99, 98.5, 99.2]
    d = frame(cl)
    assert T.evaluate(rec(d, 79), d, cfg=CFG)["state"] == T.NO_EXP
    assert T.evaluate(rec(d, 79), d.iloc[:83], cfg=CFG)["state"] == T.WATCH   # 5일이 안 지났으면 감시 유지


def test_signal_enters_on_log_day_and_stop_gap():
    cl = base() + [101, 100, 85]
    op = cl[:-1] + [88]                                 # 마지막 날 시가가 손절가(91.08) 아래 → 시가 청산
    d = frame(cl, opens=op)
    r = T.evaluate(rec(d, 80, status="진입 신호 확인"), d, cfg=CFG)
    assert r["entry"] == 101 and r["state"] == T.CLOSED and r["exit_reason"] == "손절(시가 갭)"
    assert r["exit_price"] == 88 and r["ret"] < 0 and r["R"] < -1
    assert r["fail20"] is True


def test_ma_exit_and_cost_and_benchmark():
    cl = base() + [101] + [104] * 5 + [70]
    lo = [x * 0.995 for x in cl[:-1]] + [94]          # 저가는 손절가 위, 종가는 50일선 아래
    op = cl[:-1] + [95]
    d = frame(cl, lows=lo, opens=op)
    b = pd.Series(np.linspace(100, 110, len(cl)), index=d.index)
    r = T.evaluate(rec(d, 80, status="진입 신호 확인", invalid=80.0), d, b, CFG)
    assert r["exit_reason"] == "50일선 이탈" and r["exit_price"] == 70
    assert abs(r["ret"] - (70 / 101 * 0.995 - 1)) < 1e-4
    assert r["bench_ret"] is not None and abs(r["excess"] - (r["ret"] - r["bench_ret"])) < 1e-4


def test_max_hold_closes():
    cl = base() + list(np.linspace(101, 140, 130))
    d = frame(cl)
    r = T.evaluate(rec(d, 80, status="진입 신호 확인", invalid=90.0), d, cfg=CFG)
    assert r["state"] == T.CLOSED and r["exit_reason"] == "최대 보유" and r["hold"] == 120


def test_zero_volume_days_ignored():
    cl = base() + [99, 99, 101]
    v = [1000] * 80 + [0, 0, 2500]
    d = frame(cl, v)
    r = T.evaluate(rec(d, 79), d, cfg=CFG)
    assert r["entry"] == 101                            # 거래정지 2일은 5일 창에 포함되지 않음


def test_new_records_dedupe_and_summary(monkeypatch):
    import types
    sys.modules.setdefault("models", types.SimpleNamespace(FORM="패턴 형성 중", SIGNAL="진입 신호 확인"))
    ms = [dict(code="000001", name="A", market="KOSPI", asof="2026-03-02", close=100.0,
               models=[dict(model="vcp", model_name="VCP", status="패턴 형성 중", pivot=101.0, invalid=92.0, score=70),
                       dict(model="flat", model_name="플랫 베이스", status="주의/무효화", pivot=101.0, invalid=92.0)])]
    a = T.new_records(ms, [], {}, CFG)
    assert len(a) == 1 and a[0]["model"] == "vcp"
    assert T.new_records(ms, a, {}, CFG) == []          # 같은 기록 재실행 → 중복 없음
    ms[0]["asof"] = "2026-03-03"
    assert T.new_records(ms, a, {}, CFG) == []          # 감시 중이면 다음 날 같은 모델 재기록 안 함
    s = T.summarize(a)
    assert s["total"] == 1 and s["by_state"] == {T.WATCH: 1}


def test_update_writes_files(tmp_path):
    cl = base() + [101, 103]
    d = frame(cl, [1000] * 80 + [2000, 1000])
    ms = [dict(code="000001", name="A", market="KOSPI", asof=d.index[79].strftime("%Y-%m-%d"), close=98.0,
               models=[dict(model="vcp", model_name="VCP", status="패턴 형성 중", pivot=100.0, invalid=92.0, score=70)])]
    import types
    sys.modules.setdefault("models", types.SimpleNamespace(FORM="패턴 형성 중", SIGNAL="진입 신호 확인"))
    codes, summ = T.update(str(tmp_path), ms, {"000001": d}, {}, lambda c, s: (c, None), "2025-01-01", CFG, "t")
    assert codes == {"000001"} and summ["by_state"] == {T.OPEN: 1}
    assert (tmp_path / "ledger.json").exists() and (tmp_path / "ledger.csv").exists()
    # 두 번째 실행(같은 날) → 기록 수 그대로
    codes2, summ2 = T.update(str(tmp_path), ms, {"000001": d}, {}, lambda c, s: (c, None), "2025-01-01", CFG, "t")
    assert summ2["total"] == 1
