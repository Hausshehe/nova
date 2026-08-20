def test_frozen_broader_runner_entrypoint_is_present():
    from trading_research.broader_campaign_runner import run_campaign
    from trading_research.research_universe import build_research_universe

    assert callable(run_campaign)
    assert len(build_research_universe()) == 104
