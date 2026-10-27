import warnings; warnings.filterwarnings("ignore")
import pickle, numpy as np, pandas as pd
df=pd.read_pickle("model_trades.pkl")
B=pickle.load(open("prices.pkl","rb"))["bench"]["Close"].astype(float)
NM={"legacy_vcp":"기존 VCP (비교 기준)","vcp":"VCP (신규)","cup":"컵 위드 핸들","c3":"3C","flat":"플랫 베이스","power":"파워 플레이"}
ix=B.index
def bret(r):
    i=ix.get_indexer([r.entry_date])[0]; j=min(i+int(r.hold),len(ix)-1); return B.iloc[j]/B.iloc[i]-1
df["bench_ret"]=df.apply(bret,axis=1); df["excess"]=df.ret-df.bench_ret
years=(pd.Timestamp("2026-09-30")-pd.Timestamp("2020-01-02")).days/365.25
def summ(g):
    R=g.R.clip(-3,None)
    top5=g.nlargest(5,"R").R.sum()
    return pd.Series({"진입수":len(g),"연평균 신호":len(g)/years,"MFE20 중앙":g.mfe20.median(),"MFE60 중앙":g[g.full60].mfe60.median(),
      "MAE20 중앙":g.mae20.median(),"20일내 실패율":g.fail20.mean(),"승률":(g.ret>0).mean(),"평균 수익률":g.ret.mean(),
      "수익률 중앙":g.ret.median(),"평균 R":g.R.mean(),"R 중앙":g.R.median(),"평균 보유일":g.hold.mean(),
      "같은 기간 지수":g.bench_ret.mean(),"지수 대비 초과":g.excess.mean(),"지수보다 나은 비율":(g.excess>0).mean(),
      "손절폭 평균":g.risk.mean(),"손절폭>8% 비율":(g.risk>0.08).mean(),"상위5건 R 합":top5,"전체 R 합":g.R.sum()})
order=["legacy_vcp","vcp","cup","c3","flat","power"]
S=df.groupby("model").apply(summ).reindex(order); S.index=[NM[k] for k in S.index]
pd.set_option("display.width",250); pd.set_option("display.max_columns",30)
print(S.round(3).T.to_string())
def sub(mask,label):
    T=df[mask].groupby("model").apply(lambda g: pd.Series({"n":len(g),"승률":(g.ret>0).mean(),"평균R":g.R.mean(),"평균수익":g.ret.mean(),"초과":g.excess.mean()})).reindex(order)
    T.index=[NM[k] for k in T.index]; print("\n==",label); print(T.round(3).to_string()); return T
A=sub(df.mkt_strong,"강한 시장(지수>50일>200일)에서 진입"); Bw=sub(~df.mkt_strong,"약한/혼조 시장에서 진입")
P1=sub(df.entry_date<"2023-01-01","2020~2022"); P2=sub(df.entry_date>="2023-01-01","2023~2026")
# 점수 구간 (진단용, 최적화 아님)
new=df[df.model!="legacy_vcp"].copy()
new["점수구간"]=new.groupby("model").score.transform(lambda s: pd.qcut(s.rank(method="first"),3,labels=["하위1/3","중간","상위1/3"]))
SC=new.groupby(["model","점수구간"]).apply(lambda g: pd.Series({"n":len(g),"점수범위":f"{g.score.min():.0f}~{g.score.max():.0f}","승률":(g.ret>0).mean(),"평균R":g.R.mean(),"실패율":g.fail20.mean(),"MFE20중앙":g.mfe20.median()})).reset_index()
SC["model"]=SC.model.map(NM); print("\n== 점수 구간별 (진단용)"); print(SC.round(3).to_string())
# 겹침: 기존 VCP와 신규 모델이 같은 종목·같은 진입일
k=lambda m:set(zip(df[df.model==m].code,df[df.model==m].entry_date))
L=k("legacy_vcp"); print("\n기존 VCP 진입 중 신규 모델과 같은 종목·같은 날 진입:", len(L & set().union(*[k(m) for m in order[1:]])),"/",len(L))
df.to_pickle("model_trades_enriched.pkl"); pd.to_pickle(dict(S=S,A=A,Bw=Bw,P1=P1,P2=P2,SC=SC),"model_summary.pkl")
