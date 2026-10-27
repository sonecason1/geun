"""점수 재설계: 학습(2020~2023) 구간에서만 항목 선택 → 검증(2024~2026.9) 구간에서 1회 확인.
규칙(결과를 보기 전에 고정):
 - 대상: 신규 5개 모델 진입 전체(기존 VCP 제외)
 - 후보 변수: 9개 점수 항목 + 손절폭(risk, 작을수록 좋다고 가정 → 부호 반대) + 진입가의 피벗 대비 괴리
 - 선택 기준: 학습 구간 전체 및 학습 내부 두 소구간(2020~21, 2022~23) 모두에서
   R(상한 10R로 자름)과의 순위상관이 +0.03 이상인 변수만 채택
 - 새 점수 = 채택 변수의 모델별 백분위 순위의 단순 평균(가중치 추정 없음)
 - 필터 후보(시장 강세, 손절폭 8%/10% 이하)도 학습 구간에서만 판단
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, json
df=pd.read_pickle("model_trades_enriched.pkl")
df=df[df.model!="legacy_vcp"].copy()
df["gap"]=df["entry"]/df["pivot"]-1
df["neg_risk"]=-df.risk
df["neg_gap"]=-df.gap
df["Rc"]=df.R.clip(upper=10)
TRAIN_END="2024-01-01"; MID="2022-01-01"
tr=df[df.entry_date<TRAIN_END]; te=df[df.entry_date>=TRAIN_END]
print("학습 n=",len(tr)," 검증 n=",len(te))
cands=["c_trend","c_pattern","c_contraction","c_volume","c_atr","c_rsi","c_rs","c_pivot","c_liquidity","neg_risk","neg_gap"]
def ic(d,c):
    # 모델별 순위상관을 진입수로 가중평균
    out=[];w=[]
    for m,g in d.groupby("model"):
        if len(g)<30 or g[c].nunique()<3: continue
        out.append(g[c].rank().corr(g.Rc.rank())); w.append(len(g))
    return np.average(out,weights=w) if out else np.nan
rows=[]
for c in cands:
    rows.append(dict(var=c,train=ic(tr,c),tr_a=ic(tr[tr.entry_date<MID],c),tr_b=ic(tr[tr.entry_date>=MID],c),test=ic(te,c)))
IC=pd.DataFrame(rows).set_index("var")
IC["채택"]=(IC[["train","tr_a","tr_b"]]>=0.03).all(axis=1)
print(IC.round(3).to_string())
sel=IC.index[IC["채택"]].tolist(); print("채택 변수:",sel)
json.dump(dict(selected=sel,train_end=TRAIN_END),open("redesign_selected.json","w"),ensure_ascii=False)
def newscore(d):
    if not sel: return pd.Series(np.nan,index=d.index)
    return d.groupby("model")[sel].rank(pct=True).mean(axis=1)
# 백분위는 구간마다 따로 계산(검증 구간 정보가 학습에 섞이지 않게)
tr=tr.assign(ns=newscore(tr)); te=te.assign(ns=newscore(te))
def terc(d,col):
    q=d.groupby("model")[col].transform(lambda s: pd.qcut(s.rank(method="first"),3,labels=["하위","중간","상위"]))
    return d.assign(q=q).groupby("q").apply(lambda g: pd.Series({"n":len(g),"승률":(g.ret>0).mean(),"평균R":g.R.mean(),"R중앙":g.R.median(),"실패율":g.fail20.mean(),"초과":g.excess.mean()}))
for lab,d in [("학습",tr),("검증",te)]:
    print(f"\n== {lab}: 기존 점수 3분위"); print(terc(d,"score").round(3).to_string())
    if sel: print(f"== {lab}: 새 점수 3분위"); print(terc(d,"ns").round(3).to_string())
def st(g): return pd.Series({"n":len(g),"승률":(g.ret>0).mean(),"평균R":g.R.mean(),"R중앙":g.R.median(),"평균수익":g.ret.mean(),"실패율":g.fail20.mean(),"초과":g.excess.mean()})
F={"전체":lambda d:d.index==d.index,"강한시장":lambda d:d.mkt_strong,"손절≤8%":lambda d:d.risk<=0.08,"손절≤10%":lambda d:d.risk<=0.10,
   "강한시장+손절≤10%":lambda d:d.mkt_strong&(d.risk<=0.10),"강한시장+손절≤8%":lambda d:d.mkt_strong&(d.risk<=0.08)}
R=[]
for lab,d in [("학습",tr),("검증",te)]:
    for k,f in F.items():
        s=st(d[f(d)]); s["구간"]=lab; s["필터"]=k; R.append(s)
FR=pd.DataFrame(R).set_index(["필터","구간"]); print("\n== 필터"); print(FR.round(3).to_string())
# 모델별 x 강한시장
print("\n== 모델별, 강한 시장 진입만")
print(pd.concat({lab:d[d.mkt_strong].groupby("model").apply(st) for lab,d in [("학습",tr),("검증",te)]}).round(3).to_string())
pd.to_pickle(dict(IC=IC,FR=FR,tr=tr,te=te),"redesign.pkl")
