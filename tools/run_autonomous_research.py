"""Run one bounded Groq-assisted research cycle from the command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_research.autonomous_research import AutonomousResearchSession
from trading_research.groq_hypothesis import GroqHypothesisGenerator, ResearchQuestion
from trading_research.memory import ExperienceStore
from trading_research.rule_dsl import compile_long_flat_rules
from trading_research.researcher import ResearchBudget


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("question")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="1D")
    parser.add_argument("--memory", type=Path, default=ROOT / "data" / "research" / "experience.sqlite3")
    parser.add_argument("--max-hypotheses", type=int, default=1)
    parser.add_argument("--max-revisions", type=int, default=0)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required")

    generator_kwargs = {}
    if args.model:
        generator_kwargs["model"] = args.model
    generator = GroqHypothesisGenerator(api_key, **generator_kwargs)
    memory = ExperienceStore(args.memory)
    session = AutonomousResearchSession(
        generator=generator,
        memory=memory,
        signal_compiler=lambda hypothesis: compile_long_flat_rules(dict(hypothesis.rules)),
        budget=ResearchBudget(
            max_hypotheses=args.max_hypotheses,
            max_revisions=args.max_revisions,
        ),
    )

    result = session.propose_and_test(
        ResearchQuestion(
            question=args.question,
            symbol=args.symbol,
            timeframe=args.timeframe,
        ),
        csv_path=str(args.csv),
    )
    output = {
        "status": result.status,
        "message": result.message,
        "fingerprint": result.fingerprint,
        "source": result.source,
        "final_decision": result.experiment.final_decision.value if result.experiment else None,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
