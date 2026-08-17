import importlib
import os
import sys

TOOLS_DIR = os.path.dirname(__file__)


def discover_tools():
    tools = {}

    importlib.invalidate_caches()

    for filename in os.listdir(TOOLS_DIR):
        if not filename.endswith(".py"):
            continue

        if filename.startswith("_") or filename == "registry.py":
            continue

        # Ignore backup/version files and maintenance scripts.
        if (
            ".before_" in filename
            or filename.startswith(("fix_", "improve_", "optimize_", "install_", "repair_"))
        ):
            continue

        module_name = filename[:-3]
        full_name = f"tools.{module_name}"

        try:
            if full_name in sys.modules:
                module = importlib.reload(sys.modules[full_name])
            else:
                module = importlib.import_module(full_name)

            tools[module_name] = module

        except Exception as e:
            print(f"⚠️ Could not load tool {module_name}: {e}")

    return tools


def list_tools():
    tools = discover_tools()

    print("\n🧰 Nova's available tools:")
    for name in tools:
        print(f"  • {name}")

    return tools
