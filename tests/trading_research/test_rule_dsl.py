import pytest

from trading_research.rule_dsl import compile_long_flat_rules


def test_rule_dsl_rejects_untrusted_syntax():
    with pytest.raises(ValueError, match="unsupported rule DSL"):
        compile_long_flat_rules(
            {
                "entry": "python(open('orders.py'))",
                "exit": "close < prior_low(10)",
                "filters": "none",
                "costs": "2 bps per side",
            }
        )


def test_rule_dsl_accepts_allow_listed_form():
    signal = compile_long_flat_rules(
        {
            "entry": "close > prior_high(20)",
            "exit": "close < prior_low(10)",
            "filters": "none",
            "costs": "2 bps per side",
        }
    )
    assert callable(signal)
