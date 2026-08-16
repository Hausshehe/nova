import os
import ast
import sys

BASE_DIR = "/data/data/com.termux/files/home/infoney"

WORKSPACE_DIR = os.path.join(
    BASE_DIR,
    "workspace"
)

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

    return name


def validate_python(code):
    try:
        ast.parse(code)
        return True, "Python syntax is valid."
    except SyntaxError as e:
        return False, str(e)


def validate_proposal(code, tool_name):
    valid, message = validate_python(code)

    if not valid:
        return False, message

    quality_ok, quality_message = check_generated_code_quality(code)

    if not quality_ok:
        return False, quality_message

    signature_ok, signature_message = check_function_signature(
        code,
        tool_name
    )

    if not signature_ok:
        return False, signature_message

    imports_ok, imports_message = check_imports(code)

    if not imports_ok:
        return False, imports_message

    subprocess_ok, subprocess_message = check_subprocess_usage(code)

    if not subprocess_ok:
        return False, subprocess_message

    return True, "Proposal passed all validation checks."


def get_proposal(tool_name):
    tool_name = safe_name(tool_name)
    function_name = tool_name[:-3]

    path = os.path.join(
        WORKSPACE_DIR,
        tool_name
    )

    if not os.path.exists(path):
        return {
            "success": False,
            "error": "No proposed tool exists."
        }

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            code = f.read()

    except OSError as e:
        return {
            "success": False,
            "error": "Could not read proposal: " + str(e)
        }

    valid, message = validate_proposal(
        code,
        function_name
    )

    if not valid:
        return {
            "success": False,
            "error": "Proposal validation failed: " + message
        }

    return {
        "success": True,
        "tool": tool_name,
        "path": path,
        "code": code,
        "message": message
    }


def request_approval(tool_name, approval_callback=None):
    proposal = get_proposal(tool_name)

    if not proposal["success"]:
        return proposal

    print("\n" + "=" * 60)
    print("🧠 NOVA TOOL APPROVAL")
    print("=" * 60)

    print(f"Tool: {proposal['tool']}")
    print(f"Path: {proposal['path']}")
    print(f"\nValidation: {proposal['message']}")

    print("\nProposed code:\n")
    print(proposal["code"])

    print("=" * 60)

    if approval_callback is not None:
        answer = approval_callback()
    else:
        answer = input("\nInstall this tool? [y/N]: ")

    answer = str(answer).strip().lower()

    if answer != "y":
        return {
            "success": False,
            "approved": False,
            "message": "Installation cancelled by user."
        }

    try:
        from tools.installer import install_tool

        result = install_tool(tool_name)

        if result["success"]:
            result["approved"] = True

        return result

    except Exception as e:
        return {
            "success": False,
            "approved": False,
            "error": "Installation failed: " + str(e)
        }


if __name__ == "__main__":
    result = request_approval(
        "volume_control"
    )

    print("\nResult:")
    print(result)
