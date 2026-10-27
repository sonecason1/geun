# -*- coding: utf-8 -*-
"""백테스트용 가격 데이터 다운로드 (코스피·코스닥 보통주, 2018-06 ~ 현재)"""
import os as _os
HERE=_os.path.dirname(_os.path.abspath(__file__))
import pickle, time, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import FinanceDataReader as fdr

warnings.filterwarnings("ignore")
START = "2018-06-01"
OUT = _os.path.join(HERE,"prices.pkl")

uni = fdr.StockListing("KRX")
uni = uni[uni["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])]
uni = uni[uni["Code"].str[-1] == "0"]
uni = uni[~uni["Name"].str.contains("스팩|SPAC|리츠|기업인수목적", regex=True)]
uni = uni[["Code", "Name", "Market"]].reset_index(drop=True)
print("대상", len(uni))


def fetch(code):
    for a in range(3):
        try:
            d = fdr.DataReader(code, START)
            if d is not None and len(d):
                d = d[["Open", "High", "Low", "Close", "Volume"]].astype("float32")
                return code, d[d["Volume"] > 0]
        except Exception:
            time.sleep(1 + a)
    return code, None


t0 = time.time()
prices = {}
with ThreadPoolExecutor(max_workers=16) as ex:
    for i, fu in enumerate(as_completed([ex.submit(fetch, c) for c in uni["Code"]]), 1):
        c, d = fu.result()
        if d is not None and len(d) > 260:
            prices[c] = d
        if i % 500 == 0:
            print(i, f"{time.time()-t0:.0f}s")
bench = fdr.DataReader("069500", START)[["Open", "High", "Low", "Close", "Volume"]]
with open(OUT, "wb") as f:
    pickle.dump(dict(prices=prices, uni=uni, bench=bench), f)
print("저장", len(prices), "종목", f"{time.time()-t0:.0f}s", bench.index[-1])
