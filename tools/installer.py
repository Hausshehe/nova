import os
import shutil
import datetime
import ast
import sys

BASE_DIR = "/data/data/com.termux/files/home/infoney"

WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

sys.path.insert(0, BASE_DIR)

from tools.ai_builder import (
    check_generated_code_quality,
    check_function_signature,
    check_imports,
    check_subprocess_usage
)


def safe_name(name):
    name = os.path.basename(name)

    if not name.endswith(".py"):
        name += ".py"

    protected = {
        "registry.py",
        "installer.py",
        "approval.py",
        "ai_builder.py",
        "self_builder.py"
    }

    if name in protected:
        raise ValueError("Protected tool cannot be replaced.")

    return name


def validate_proposal(code, tool_name):

    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, str(e)

    ok, message = check_generated_code_quality(code)
    if not ok:
        return False, message

    ok, message = check_function_signature(code, tool_name)
    if not ok:
        return False, message

    ok, message = check_imports(code)
    if not ok:
        return False, message

    ok, message = check_subprocess_usage(code)
    if not ok:
        return False, message

    return True, "Tool passed final validation."


def install_tool(tool_name):

    try:
        tool_name = safe_name(tool_name)
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }

    function_name = tool_name[:-3]

    source = os.path.join(
        WORKSPACE_DIR,
        tool_name
    )

    destination = os.path.join(
        TOOLS_DIR,
        tool_name
    )

    if not os.path.exists(source):
        return {
            "success": False,
            "error": "No proposed tool found."
        }

    with open(
        source,
        "r",
        encoding="utf-8"
    ) as f:
        code = f.read()

    valid, message = validate_proposal(
        code,
        function_name
    )

    if not valid:
        return {
            "success": False,
            "error": "Final validation failed: " + message
        }

    os.makedirs(
        BACKUP_DIR,
        exist_ok=True
    )

    backup = None

    if os.path.exists(destination):

        timestamp = datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        backup = os.path.join(
            BACKUP_DIR,
            f"{tool_name}.{timestamp}.bak"
        )

        shutil.copy2(
            destination,
            backup
        )

    try:

        shutil.copy2(
            source,
            destination
        )

    except OSError as e:

        if backup and os.path.exists(backup):
            shutil.copy2(
                backup,
                destination
            )

        return {
            "success": False,
            "error": "Installation failed: " + str(e)
        }

    return {
        "success": True,
        "installed": destination,
        "backup": backup,
        "message": message
    }


if __name__ == "__main__":

    print(
        install_tool("hello_test")
    )
