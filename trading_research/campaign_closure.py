"""Executable guard for finite research campaigns.

The guard is checked before proposal generation. A closed campaign requires a
materially new evidence source or a materially new market question before it
can be restarted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


CURRENT_EURUSD_DATASET_SHA256 = (
    "e4c70add8d77bcf5aa97ea9eeaa08d0fc8cc91679e6fd6a85ee3ad4a913b7f9e"
)
CURRENT_CAMPAIGN_MAX_FAMILIES = 5


@dataclass(frozen=True)
class CampaignState:
    dataset_sha256: str
    completed_families: tuple[str, ...]
    max_families: int = CURRENT_CAMPAIGN_MAX_FAMILIES
    closed: bool = False

    @property
    def family_count(self) -> int:
        return len(self.completed_families)


@dataclass(frozen=True)
class CampaignClosureDecision:
    action: str
    reason: str
    family_count: int
    max_families: int


def evaluate_campaign_closure(
    state: CampaignState,
    *,
    dataset_sha256: str | None,
    market_question_changed: bool = False,
) -> CampaignClosureDecision:
    """Return the deterministic campaign-level planning decision."""
    if market_question_changed:
        return CampaignClosureDecision(
            action="ALLOW_RESTART_NEW_MARKET_QUESTION",
            reason="The market question is materially new; start a deliberately scoped research campaign.",
            family_count=state.family_count,
            max_families=state.max_families,
        )

    if dataset_sha256 is None or dataset_sha256 == state.dataset_sha256:
        if state.closed or state.family_count >= state.max_families:
            return CampaignClosureDecision(
                action="CAMPAIGN_CLOSED",
                reason="The finite campaign is closed; the current evidence source cannot generate another hypothesis family.",
                family_count=state.family_count,
                max_families=state.max_families,
            )

    if dataset_sha256 != state.dataset_sha256:
        return CampaignClosureDecision(
            action="ALLOW_RESTART_NEW_EVIDENCE",
            reason="The evidence source is materially new; the campaign may be restarted with fresh provenance.",
            family_count=state.family_count,
            max_families=state.max_families,
        )

    return CampaignClosureDecision(
        action="ALLOW_CONTINUE",
        reason="The campaign remains within its frozen family budget.",
        family_count=state.family_count,
        max_families=state.max_families,
    )


def current_eurusd_campaign_state() -> CampaignState:
    """Canonical closed state for the completed EURUSD research campaign."""
    return CampaignState(
        dataset_sha256=CURRENT_EURUSD_DATASET_SHA256,
        completed_families=(
            "horizon_expert_adaptation",
            "volatility_mean_reversion",
            "donchian_breakout",
            "friday_continuation",
            "positive_opening_gap",
        ),
        max_families=CURRENT_CAMPAIGN_MAX_FAMILIES,
        closed=True,
    )
