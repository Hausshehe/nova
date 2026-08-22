from unittest.mock import patch

from navigation.actions import activate_node, scroll


class _Snapshot:
    scrollable_regions = [
        {"bounds": "[0,200][1080,2100]"},
    ]


def test_tap_uses_live_bounds_with_root_fallback():
    node = {
        "text": "Apps",
        "content_description": "",
        "resource_id": "",
        "bounds": "[120,500][960,700]",
        "clickable": True,
        "enabled": True,
    }

    with patch("navigation.actions._accessibility_click", return_value=(False, "receiver rejected", 1, 10.0)):
        with patch("navigation.actions._root_input", return_value=(True, "tap ok", 0, 20.0)) as root:
            result = activate_node(node)

    assert result.success is True
    assert result.action == "TAP"
    root.assert_called_once_with("input tap 540 600")


def test_scroll_uses_root_swipe_when_accessibility_scroll_is_rejected():
    with patch("navigation.actions._accessibility_scroll", return_value=(False, "receiver rejected", 1, 10.0)):
        with patch("navigation.actions._root_input", return_value=(True, "swipe ok", 0, 20.0)) as root:
            result = scroll(_Snapshot(), "down", distance_ratio=0.35)

    assert result.success is True
    assert result.action == "SCROLL"
    command = root.call_args.args[0]
    assert command.startswith("input swipe 540 ")
    assert command.endswith(" 280")


def test_scroll_rejects_invalid_live_region_before_fallback():
    class BadSnapshot:
        scrollable_regions = [{"bounds": "[0,0][20,20]"}]

    with patch("navigation.actions._accessibility_scroll") as accessibility:
        with patch("navigation.actions._root_input") as root:
            result = scroll(BadSnapshot(), "down")

    assert result.success is False
    accessibility.assert_not_called()
    root.assert_not_called()
