import importlib
import time


# Android Activities and accessibility UI updates are asynchronous. Give the
# framework a short settling window before Nova immediately asks UIAutomator
# for the next hierarchy snapshot. This is intentionally limited to
# state-changing Android primitives whose tools do not already perform their
# own settle delay.
POST_ACTION_SETTLE_SECONDS = 0.75
STATE_CHANGING_TOOLS = {
    "launch_android_app",
    "click_text",
    "click_node",
    "type_text",
    "back_android",
}


def execute_tool(tool_name, function_name, **kwargs):
    try:
        module = importlib.import_module(
            f"tools.{tool_name}"
        )

        function = getattr(module, function_name)

        result = function(**kwargs)

        if (
            tool_name in STATE_CHANGING_TOOLS
            and isinstance(result, dict)
            and result.get("success")
        ):
            time.sleep(POST_ACTION_SETTLE_SECONDS)

        return {
            "success": True,
            "result": result
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
