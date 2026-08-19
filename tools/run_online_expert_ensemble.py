from __future__ import annotations
import argparse, json
from trading_research.data import load_csv
from trading_research.online_expert_ensemble import evaluate_online_expert_ensemble

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("dataset")
    p.add_argument("output")
    a=p.parse_args()
    result=evaluate_online_expert_ensemble(load_csv(a.dataset))
    with open(a.output,"w",encoding="utf-8") as f: json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))

if __name__ == "__main__": main()
