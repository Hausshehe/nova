from trading_research.data import Bar
from trading_research.online_expert_ensemble import evaluate_online_expert_ensemble, EXPERTS

def test_online_expert_ensemble_returns_causal_report():
    bars=[Bar(f"2020-01-{(i%28)+1:02d}",100+i*0.1,101+i*0.1,99+i*0.1,100+i*0.1,1) for i in range(700)]
    r=evaluate_online_expert_ensemble(bars, folds=4)
    assert r["policy"]=="causal_online_expert_ensemble"
    assert tuple(r["experts"])==EXPERTS
    assert len(r["fold_net_returns"])==4
    assert "evaluation-only" in r["causal_rule"]
