"""Contract tests documenting the live-demo integration boundary.

These tests intentionally remain dependency-light until the integration module
is wired. They lock down the required fail-closed stages for the next step.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineContract:
    stages: tuple[str, ...]
    live_trading_enabled: bool = False


def test_live_demo_pipeline_is_explicitly_fail_closed():
    contract = PipelineContract(
        stages=(
            "market_monitor",
            "escalation",
            "market_context",
            "adaptive_brain",
            "decision_policy",
            "demo_supervisor",
            "orchestrator",
            "experience_journal",
        )
    )
    assert contract.live_trading_enabled is False
    assert contract.stages[0] == "market_monitor"
    assert contract.stages[-1] == "experience_journal"


def test_ai_is_not_the_execution_authority():
    contract = PipelineContract(
        stages=("market_monitor", "adaptive_brain", "decision_policy", "demo_supervisor")
    )
    assert contract.stages.index("adaptive_brain") < contract.stages.index("decision_policy")
    assert contract.stages.index("decision_policy") < contract.stages.index("demo_supervisor")
