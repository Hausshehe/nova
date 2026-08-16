import importlib


def execute_tool(tool_name, function_name, **kwargs):
    try:
        module = importlib.import_module(
            f"tools.{tool_name}"
        )

        function = getattr(module, function_name)

        result = function(**kwargs)

        return {
            "success": True,
            "result": result
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
