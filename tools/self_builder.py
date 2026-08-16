import os
import re
import ast


BASE_DIR = "/data/data/com.termux/files/home/infoney"

WORKSPACE_DIR = os.path.join(
    BASE_DIR,
    "workspace"
)


def safe_name(name):
    name = name.lower().strip()

    name = re.sub(
        r"[^a-z0-9_]+",
        "_",
        name
    )

    name = name.strip("_")

    if not name:
        raise ValueError("Invalid tool name")

    return name


def validate_python(code):
    try:
        ast.parse(code)
        return True, "Python syntax is valid."

    except SyntaxError as e:
        return False, str(e)


def create_proposal(tool_name, code):

    tool_name = safe_name(tool_name)

    os.makedirs(
        WORKSPACE_DIR,
        exist_ok=True
    )

    path = os.path.join(
        WORKSPACE_DIR,
        tool_name + ".py"
    )

    valid, message = validate_python(code)

    if not valid:
        return {
            "success": False,
            "error": message
        }

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(code)

    return {
        "success": True,
        "path": path,
        "message": message
    }


def show_proposal(tool_name):

    tool_name = safe_name(tool_name)

    path = os.path.join(
        WORKSPACE_DIR,
        tool_name + ".py"
    )

    if not os.path.exists(path):

        return {
            "success": False,
            "error": "Proposal does not exist."
        }

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        code = f.read()

    return {
        "success": True,
        "path": path,
        "code": code
    }


if __name__ == "__main__":

    example = '''def hello():
    return "Hello from Nova!"
'''

    result = create_proposal(
        "hello_test",
        example
    )

    print(result)

    if result["success"]:

        print("\n📄 Proposed code:\n")

        proposal = show_proposal(
            "hello_test"
        )

        print(proposal["code"])
