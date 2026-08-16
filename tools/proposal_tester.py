import os
import ast
import importlib.util


BASE_DIR = "/data/data/com.termux/files/home/infoney"

WORKSPACE_DIR = os.path.join(
    BASE_DIR,
    "workspace"
)


def load_proposal(tool_name):

    if not tool_name.endswith(".py"):
        tool_name += ".py"

    path = os.path.join(
        WORKSPACE_DIR,
        tool_name
    )

    if not os.path.exists(path):
        return None, "Proposal does not exist."

    with open(path, "r", encoding="utf-8") as f:
        code = f.read()

    return code, path


def check_syntax(code):

    try:
        ast.parse(code)

        return True, "Python syntax is valid."

    except SyntaxError as e:

        return False, str(e)


def check_structure(code, tool_name):

    tree = ast.parse(code)

    expected_name = tool_name.replace(".py", "")

    functions = [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]

    if expected_name not in functions:
        return False, (
            f"Required function '{expected_name}' was not found."
        )

    if len(functions) != 1:
        return False, (
            "Tool must contain exactly one main public function."
        )

    return True, "Tool structure is valid."


def check_safety(code):

    tree = ast.parse(code)

    dangerous = [
        "eval",
        "exec",
        "__import__"
    ]

    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            if isinstance(node.func, ast.Name):

                if node.func.id in dangerous:

                    return False, (
                        f"Potentially dangerous operation detected: "
                        f"{node.func.id}"
                    )

    return True, "Basic safety checks passed."


def check_import(tool_name):

    if not tool_name.endswith(".py"):
        tool_name += ".py"

    path = os.path.join(
        WORKSPACE_DIR,
        tool_name
    )

    module_name = "proposal_" + tool_name[:-3]

    try:

        spec = importlib.util.spec_from_file_location(
            module_name,
            path
        )

        module = importlib.util.module_from_spec(spec)

        spec.loader.exec_module(module)

        return True, "Tool imported successfully."

    except Exception as e:

        return False, f"Import failed: {e}"


def test_proposal(tool_name):

    print()
    print("🧪 NOVA PROPOSAL TEST")
    print("=" * 50)

    code, result = load_proposal(tool_name)

    if code is None:

        print("❌", result)

        return {
            "success": False,
            "error": result
        }

    print("📄 Proposal:", result)

    valid, message = check_syntax(code)

    print("1️⃣ Syntax:", message)

    if not valid:

        return {
            "success": False,
            "stage": "syntax",
            "error": message
        }

    valid, message = check_structure(
        code,
        tool_name
    )

    print("2️⃣ Structure:", message)

    if not valid:

        return {
            "success": False,
            "stage": "structure",
            "error": message
        }

    valid, message = check_safety(code)

    print("3️⃣ Safety:", message)

    if not valid:

        return {
            "success": False,
            "stage": "safety",
            "error": message
        }

    valid, message = check_import(tool_name)

    print("4️⃣ Import:", message)

    if not valid:

        return {
            "success": False,
            "stage": "import",
            "error": message
        }

    print("=" * 50)
    print("✅ Proposal passed basic tests.")

    return {
        "success": True,
        "message": "Proposal passed all basic tests."
    }

def functional_test_volume_control():

    print()
    print("🔬 Functional test: volume_control")

    try:
        import subprocess
        import json

        def get_music_volume():

            result = subprocess.run(
                ["termux-volume"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "termux-volume failed."
                )

            data = json.loads(result.stdout)

            for stream in data:

                if stream.get("stream") == "music":
                    return (
                        stream["volume"],
                        stream["max_volume"]
                    )

            raise RuntimeError(
                "Music stream was not found."
            )

        original, maximum = get_music_volume()

        print(
            f"🔊 Current music volume: "
            f"{original}/{maximum}"
        )

        if original >= maximum:

            print(
                "⚠️ Volume is already at maximum."
            )

            return {
                "success": False,
                "message": "Cannot test increase because volume is already maximum."
            }

        expected = original + 1

        print(
            f"➡️ Testing increase to {expected}"
        )

        module_path = os.path.join(
            WORKSPACE_DIR,
            "volume_control.py"
        )

        spec = importlib.util.spec_from_file_location(
            "proposal_volume_control",
            module_path
        )

        module = importlib.util.module_from_spec(spec)

        spec.loader.exec_module(module)

        result = module.volume_control("up")

        print("⚙️ Tool result:", result)

        actual, _ = get_music_volume()

        print(
            f"🔊 Volume after test: "
            f"{actual}/{maximum}"
        )

        # Restore original volume.

        subprocess.run(
            [
                "termux-volume",
                "music",
                str(original)
            ],
            capture_output=True,
            text=True
        )

        restored, _ = get_music_volume()

        print(
            f"🔄 Restored volume: "
            f"{restored}/{maximum}"
        )

        if actual != expected:

            return {
                "success": False,
                "message": (
                    f"Functional test failed. "
                    f"Expected {expected}, got {actual}."
                )
            }

        if restored != original:

            return {
                "success": False,
                "message": (
                    "Volume changed correctly but "
                    "could not be restored."
                )
            }

        return {
            "success": True,
            "message": "Volume control functional test passed."
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }
if __name__ == "__main__":

    result = test_proposal(
        "volume_control"
    )

    print()

    if result["success"]:

        functional = functional_test_volume_control()

        print()
        print("📊 Functional result:")
        print(functional)

        if not functional["success"]:
            result = functional

    print()
    print("📊 Final result:")
    print(result)
