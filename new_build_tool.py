def build_tool_definitions():

    tool_definitions = []

    discovered = discover_tools()

    for name, module in discovered.items():

        if name in INTERNAL_TOOLS:
            continue

        function = getattr(module, name, None)

        if function is None:
            continue

        signature = inspect.signature(function)

        properties = {}
        required = []

        for parameter_name, parameter in signature.parameters.items():

            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD
            ):
                continue

            parameter_type = get_parameter_type(
                parameter_name,
                parameter
            )

            property_definition = {
                "type": parameter_type,
                "description": (
                    f"Parameter '{parameter_name}' "
                    f"for {name}."
                )
            }

            if name == "volume_control" and parameter_name == "action":
                property_definition["enum"] = [
                    "up",
                    "down",
                    "set"
                ]

            properties[parameter_name] = property_definition

            if parameter.default is inspect.Parameter.empty:
                required.append(parameter_name)

        tool_definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": f"Use the {name} tool.",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        })

    tool_definitions.append({
        "type": "function",
        "function": {
            "name": "open_mt5",
            "description": (
                "Open the MetaTrader 5 Android application."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    })

    return tool_definitions
