from __future__ import annotations
import argparse, json
from trading_research.data import load_csv
from trading_research.hybrid_ai_adjudication import evaluate_hybrid_ai_adjudication


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("output")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    args = parser.parse_args()
    result = evaluate_hybrid_ai_adjudication(load_csv(args.dataset), limit=args.limit, model=args.model)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
