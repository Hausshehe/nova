from trading_research.hybrid_ai_adjudication import evaluate_hybrid_ai_adjudication


def test_limit_validation():
    try:
        evaluate_hybrid_ai_adjudication([], limit=0)
    except ValueError:
        return
    raise AssertionError("limit=0 must fail")
