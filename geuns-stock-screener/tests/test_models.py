# -*- coding: utf-8 -*-
"""진입모델 테스트: python -m pytest tests -q"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path[:0] = [os.path.join(os.path.dirname(__file__), "..", "screener"), os.path.dirname(__file__)]
import indicators as I  # noqa: E402
import models as M  # noqa: E402
import synth as S  # noqa: E402

CFG = M.load_config()


def by_model(res):
    return {e["model"]: e for e in res["models"]}


# ───────── 지표 계산 기간 검증 ─────────
def _rsi_ref(c, n):
    d = np.diff(c)
    g, l = np.clip(d, 0, None), np.clip(-d, 0, None)
    ag, al = g[:n].mean(), l[:n].mean()
    out = [np.nan] * (n + 1)
    out[n] = 100 - 100 / (1 + ag / al)
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
        out.append(100 - 100 / (1 + ag / al))
    return np.array(out)


def test_rsi_wilder_and_period():
    c = 100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 120))
    r = I.rsi(c, 14)
    assert np.isnan(r[13]) and np.isfinite(r[14])          # 14개 변화가 쌓인 인덱스 14부터 유효
    np.testing.assert_allclose(r[14:], _rsi_ref(c, 14)[14:], rtol=1e-9)


def test_rsi_all_up_is_100():
    assert I.rsi(np.arange(1, 40, dtype=float), 14)[-1] == 100


def test_atr_wilder_and_period():
    rng = np.random.default_rng(2)
    c = 100 + np.cumsum(rng.normal(0, 1, 80)); h = c + 1; l = c - 1
    a = I.atr(h, l, c, 14)
    assert np.isnan(a[12]) and np.isfinite(a[13])
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, abs(h - pc), abs(l - pc)]), axis=0); tr[0] = h[0] - l[0]
    assert a[13] == pytest.approx(tr[:14].mean())
    assert a[14] == pytest.approx((a[13] * 13 + tr[14]) / 14)


def test_volume_windows_exclude_current_day():
    v = np.r_[np.full(70, 100.0), 1000.0]
    assert I.breakout_volume_mult(v, 70, 50) == pytest.approx(10.0)     # 당일은 평균에 포함 안 됨
    v2 = np.r_[np.full(20, 100.0), np.full(5, 50.0), 9999.0]
    assert I.volume_dry_ratio(v2, 25, 5, 20) == pytest.approx(0.5)      # end(=25) 미포함


# ───────── 모델별 정상 사례 ─────────
CASES = [("vcp", "vcp"), ("cup", "cup"), ("cheat", "c3"), ("flat", "flat"), ("power", "power")]


@pytest.mark.parametrize("gen,key", CASES)
def test_pattern_forming_day_before_breakout(gen, key):
    df, tb = getattr(S, gen)()
    res = M.analyze_stock(df.iloc[:tb], S.bench_for(df), CFG)
    e = by_model(res).get(key)
    assert e is not None, res["rejections"].get(key)
    assert e["status"] == M.FORM, e["detail"]


@pytest.mark.parametrize("gen,key", CASES)
def test_breakout_signal_on_breakout_day(gen, key):
    df, tb = getattr(S, gen)()
    res = M.analyze_stock(df.iloc[:tb + 1], S.bench_for(df), CFG)
    e = by_model(res).get(key)
    assert e is not None, res["rejections"].get(key)
    assert e["status"] == M.SIGNAL, e["detail"]
    assert e["brk_mult"] >= CFG["volume"]["breakout_mult"]


def test_breakout_without_volume_is_not_signal():
    df, tb = S.vcp(mult=0.8)
    e = by_model(M.analyze_stock(df.iloc[:tb + 1], S.bench_for(df), CFG)).get("vcp")
    assert e is not None and e["status"] != M.SIGNAL


def test_power_play_not_penalized_for_high_rsi():
    df, tb = S.power()
    res = M.analyze_stock(df.iloc[:tb], S.bench_for(df), CFG)
    e = by_model(res)["power"]
    if res["rsi"] is not None and res["rsi"] > CFG["rsi"]["overbought"]:
        assert e["components"]["rsi"] == 1.0
    assert e["components"]["rsi"] >= 0.8


# ───────── 실패 사례 ─────────
def test_downtrend_not_a_candidate():
    df = S.downtrend()
    res = M.analyze_stock(df, S.bench_for(df), CFG)
    for k in ["vcp", "cup", "flat"]:
        e = by_model(res).get(k)
        assert e is None or e["status"] == M.WARN, (k, e and e["detail"])


def test_loose_base_not_vcp():
    df = S.loose()
    e = by_model(M.analyze_stock(df, S.bench_for(df), CFG)).get("vcp")
    assert e is None or e["status"] != M.SIGNAL


def test_close_below_invalidation_is_warn():
    df, tb = S.vcp()
    base = M.analyze_stock(df.iloc[:tb], S.bench_for(df), CFG)
    inv = by_model(base)["vcp"]["invalid"]
    d2 = df.iloc[:tb].copy()
    d2.iloc[-1, d2.columns.get_loc("Close")] = inv * 0.97
    d2.iloc[-1, d2.columns.get_loc("Low")] = inv * 0.96
    e = by_model(M.analyze_stock(d2, S.bench_for(df), CFG)).get("vcp")
    assert e is None or e["status"] == M.WARN


# ───────── 데이터 부족·품질 ─────────
def test_data_shortage_all_models():
    df, _ = S.vcp()
    res = M.analyze_stock(df.iloc[:60], S.bench_for(df), CFG)
    assert [e["status"] for e in res["models"]] == [M.NODATA]


def test_data_shortage_long_models_but_power_checked():
    df, _ = S.vcp()
    res = M.analyze_stock(df.iloc[-150:], S.bench_for(df), CFG)
    assert any(e["status"] == M.NODATA for e in res["models"])
    assert set(res["rejections"]) | {e["model"] for e in res["models"]} <= {"power", "data"}


def test_zero_volume_days_flagged():
    df, tb = S.vcp()
    d = df.iloc[:tb].copy()
    d.iloc[-30:-20, d.columns.get_loc("Volume")] = 0
    res = M.analyze_stock(d, S.bench_for(df), CFG)
    assert any("거래정지" in w for w in res["warnings"])


def test_price_discontinuity_flagged():
    df, tb = S.vcp()
    d = df.iloc[:tb].copy()
    d.iloc[:-40, :4] = d.iloc[:-40, :4] * 2          # 분할 미반영처럼 과거 가격 2배
    res = M.analyze_stock(d, S.bench_for(df), CFG)
    assert any("불연속" in w for w in res["warnings"])


def test_no_benchmark_records_reason_and_scores_without_rs():
    df, tb = S.vcp()
    res = M.analyze_stock(df.iloc[:tb], None, CFG)
    assert res["rs_na"] == "벤치마크 데이터 없음"
    e = by_model(res)["vcp"]
    assert e["components"]["rs"] is None
    assert e["score_max"] == pytest.approx(100 - CFG["models"]["vcp"]["weights"]["rs"])


# ───────── 룩어헤드 방지 ─────────
@pytest.mark.parametrize("gen,key", CASES)
def test_pivot_does_not_depend_on_current_bar(gen, key):
    """기준일 봉(가격·거래량)을 바꿔도 피벗·무효화 가격은 그대로여야 한다 (구조는 전날까지로 계산)"""
    df, tb = getattr(S, gen)()
    a = by_model(M.analyze_stock(df.iloc[:tb], S.bench_for(df), CFG, recent=False)).get(key)
    d2 = df.iloc[:tb].copy()
    d2.iloc[-1] = [d2["Close"].iloc[-2]] * 4 + [d2["Volume"].iloc[-1] * 5]
    b = by_model(M.analyze_stock(d2, S.bench_for(df), CFG, recent=False)).get(key)
    assert a is not None and b is not None
    assert (a["pivot"], a["invalid"]) == (b["pivot"], b["invalid"])


def test_past_result_unchanged_by_future_bars():
    """과거 시점 판정은 그 뒤 데이터를 붙여 넣어도(같은 날까지 잘라 넣으면) 동일"""
    df, tb = S.vcp()
    r1 = M.analyze_stock(df.iloc[:tb], S.bench_for(df), CFG)
    r2 = M.analyze_stock(df.iloc[:len(df)].iloc[:tb], S.bench_for(df), CFG)
    assert [(e["model"], e["pivot"], e["status"]) for e in r1["models"]] == \
           [(e["model"], e["pivot"], e["status"]) for e in r2["models"]]
