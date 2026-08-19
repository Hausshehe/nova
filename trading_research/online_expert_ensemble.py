"""Causal online ensemble of fixed directional experts."""
from __future__ import annotations
from dataclasses import dataclass
from math import exp
from statistics import mean
from typing import Sequence
from .data import Bar
from .high_recall_candidate_policy import high_recall_candidate_indices

EXPERTS = ("sma","mom4","mom8","mom12","contrarian4","contrarian8","long_only","short_only")

@dataclass(frozen=True)
class EnsemblePrediction:
    index: int
    expert: str
    direction: str
    score: float
    net_return_bps: float

def _sma_direction(c: Sequence[float], i: int) -> str | None:
    if i < 49: return None
    fast=mean(c[i-19:i+1]); slow=mean(c[i-49:i+1])
    if fast == slow: return None
    return "LONG" if fast > slow else "SHORT"

def _momentum(c: Sequence[float], i: int, h: int) -> str | None:
    if i < h: return None
    move=c[i]/c[i-h]-1.0
    if move == 0: return None
    return "LONG" if move > 0 else "SHORT"

def _direction(c: Sequence[float], i: int, expert: str) -> str | None:
    if expert == "sma": return _sma_direction(c,i)
    if expert == "mom4": return _momentum(c,i,4)
    if expert == "mom8": return _momentum(c,i,8)
    if expert == "mom12": return _momentum(c,i,12)
    if expert == "contrarian4":
        d=_momentum(c,i,4); return None if d is None else ("SHORT" if d=="LONG" else "LONG")
    if expert == "contrarian8":
        d=_momentum(c,i,8); return None if d is None else ("SHORT" if d=="LONG" else "LONG")
    if expert == "long_only": return "LONG"
    if expert == "short_only": return "SHORT"
    raise ValueError(f"unknown expert: {expert}")

def evaluate_online_expert_ensemble(bars: Sequence[Bar], *, future_bars: int=4, transaction_cost_bps: float=4.0, half_life: float=60.0, min_history: int=120, folds: int=4) -> dict[str, object]:
    if future_bars <= 0 or half_life <= 0 or min_history < 0 or folds <= 0: raise ValueError("invalid parameters")
    candidates=sorted(high_recall_candidate_indices(bars, fast_period=20, slow_period=50))
    c=[b.close for b in bars]
    scores={e:0.0 for e in EXPERTS}; observations={e:0 for e in EXPERTS}
    predictions=[]; fold_values=[[] for _ in range(folds)]; decay=exp(-1.0/half_life)
    processed=set()
    for i in candidates:
        cutoff=i-future_bars
        for j in candidates:
            if j>cutoff: break
            if j in processed: continue
            processed.add(j)
            if j+future_bars>=len(bars): continue
            raw=(c[j+future_bars]/c[j]-1.0)*10000.0
            for e in EXPERTS:
                d=_direction(c,j,e)
                if d is None: continue
                signed=raw if d=="LONG" else -raw
                net=signed-transaction_cost_bps
                scores[e]=decay*scores[e]+(1-decay)*net
                observations[e]+=1
        if min(observations.values()) < min_history: continue
        ranked=sorted(EXPERTS,key=lambda e:scores[e],reverse=True)
        best,second=ranked[0],ranked[1]
        if scores[best] <= 0: continue
        d=_direction(c,i,best)
        if d is None or i+future_bars>=len(bars): continue
        raw=(c[i+future_bars]/c[i]-1.0)*10000.0
        signed=raw if d=="LONG" else -raw; net=signed-transaction_cost_bps
        fold=min(folds-1,i*folds//len(bars)); fold_values[fold].append(net)
        predictions.append(EnsemblePrediction(i,best,d,scores[best]-scores[second],net))
    nets=[p.net_return_bps for p in predictions]
    fold_net=[mean(v) if v else 0.0 for v in fold_values]
    return {"policy":"causal_online_expert_ensemble","experts":EXPERTS,"candidate_bars":len(candidates),"decisions":len(predictions),"decision_rate":len(predictions)/len(candidates) if candidates else 0.0,"mean_net_return_bps":mean(nets) if nets else 0.0,"positive_net_rate":sum(v>0 for v in nets)/len(nets) if nets else 0.0,"fold_net_returns":fold_net,"folds_positive":sum(v>0 for v in fold_net),"parameters":{"future_bars":future_bars,"transaction_cost_bps":transaction_cost_bps,"half_life":half_life,"min_history":min_history,"folds":folds},"causal_rule":"Expert scores use only outcomes whose horizons completed before the current decision; future outcomes are evaluation-only."}
