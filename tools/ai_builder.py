import os
import sys
import ast
import requests

sys.path.insert(
    0,
    "/data/data/com.termux/files/home/infoney"
)

from tools.self_builder import create_proposal


API_URL = "https://api.groq.com/openai/v1/chat/completions"


# ============================================================
# VERIFIED DEVICE CAPABILITIES
# ============================================================

VERIFIED_DEVICE_CAPABILITIES = """
DEVICE: Android phone running Termux.

VERIFIED:

1. Termux is installed and available.

2. The Termux command `termux-volume` is installed and works.

3. Running:

   termux-volume

   returns a JSON ARRAY.

4. Each item contains:

   stream
   volume
   max_volume

5. Example:

   [
       {
           "stream": "music",
           "volume": 11,
           "max_volume": 15
       }
   ]

6. To set a volume stream:

   termux-volume STREAM LEVEL

7. For example:

   termux-volume music 12

8. The correct Python approach is:

   subprocess.check_call(
       ["termux-volume", stream, str(new_level)]
   )

9. The output of `termux-volume` must be parsed using json.loads()
   and treated as a LIST, not a dictionary.

IMPORTANT:

Do NOT invent Android APIs.

Do NOT use Android ACTION_VOLUME intents for volume control.

Do NOT use:

   termux-volume music up

Do NOT use:

   termux-volume music down

Do NOT assume a command works unless it is known or verified.

If a capability is not covered by the verified device information,
prefer a safe implementation using standard Python/Termux mechanisms
or return an error rather than inventing an unsupported command.
"""


# ============================================================
# VERIFIED DEVICE KNOWLEDGE
# ============================================================

BASE_DIR = "/data/data/com.termux/files/home/infoney"
DEVICE_KNOWLEDGE_FILE = os.path.join(
    BASE_DIR,
    "device_knowledge.json"
)


def load_device_knowledge():
    try:
        import json

        with open(
            DEVICE_KNOWLEDGE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception as e:
        return {
            "device": "Android phone running Termux",
            "verified_capabilities": {},
            "error": str(e)
        }


def save_verified_capability(
    name,
    command,
    output,
    fields=None
):
    import json

    if not name:
        return {
            "success": False,
            "error": "Capability name is required."
        }

    knowledge = load_device_knowledge()

    if not isinstance(knowledge, dict):
        knowledge = {
            "device": "Android phone running Termux",
            "verified_capabilities": {}
        }

    capabilities = knowledge.setdefault(
        "verified_capabilities",
        {}
    )

    capability = {
        "command": command,
        "output": output,
        "verified": True
    }

    if fields:
        capability["fields"] = fields

    capabilities[name] = capability

    temporary_file = DEVICE_KNOWLEDGE_FILE + ".tmp"

    try:
        with open(
            temporary_file,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                knowledge,
                f,
                indent=2
            )
            f.write("\n")

        os.replace(
            temporary_file,
            DEVICE_KNOWLEDGE_FILE
        )

        return {
            "success": True,
            "verified": True,
            "capability": name,
            "message": (
                f"Verified capability '{name}' "
                "saved to device knowledge."
            )
        }

    except Exception as e:

        try:
            if os.path.exists(temporary_file):
                os.remove(temporary_file)
        except Exception:
            pass

        return {
            "success": False,
            "verified": False,
            "error": str(e)
        }


def get_verified_device_capabilities():
    return load_device_knowledge()


# ============================================================
# BASIC SYNTAX VALIDATION
# ============================================================


# ============================================================

def validate_generated_code(code):
    try:
        ast.parse(code)
        return True, "Python syntax is valid."
    except SyntaxError as e:
        return False, str(e)


# ============================================================
# SECURITY / QUALITY VALIDATION
# ============================================================

def check_generated_code_quality(code):

    forbidden_patterns = [
        ("shell=True", "shell=True is not allowed."),
        ("os.system(", "os.system() is not allowed."),
        ("input(", "input() is not allowed."),
        ("eval(", "eval() is not allowed."),
        ("exec(", "exec() is not allowed."),
        ("os.popen(", "os.popen() is not allowed."),
        ("subprocess.Popen(", "subprocess.Popen() is not allowed."),
    ]

    for pattern, message in forbidden_patterns:
        if pattern in code:
            return False, message

    return True, "Generated code passed quality checks."


# ============================================================
# FUNCTION VALIDATION
# ============================================================

def check_function_signature(code, tool_name):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, "Could not parse code: " + str(e)

    functions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    target = next(
        (function for function in functions if function.name == tool_name),
        None
    )

    if target is None:
        return False, f"Required function '{tool_name}' was not found."

    if len(functions) != 1:
        return False, (
            "Generated tool must contain exactly one main public function."
        )

    positional = target.args.posonlyargs + target.args.args

    # Tool-specific signatures.
    if tool_name == "volume_control":
        expected = ["action", "stream", "level"]

        if [arg.arg for arg in positional] != expected:
            return False, (
                "volume_control must use exactly: "
                "action, stream, level."
            )

        if len(target.args.defaults) != 2:
            return False, (
                "volume_control requires defaults for "
                "stream and level."
            )

    else:
        # Generic tools currently receive no arguments unless
        # their specification explicitly defines them later.
        if positional or target.args.kwonlyargs:
            return False, (
                f"{tool_name} must not require undocumented arguments."
            )

    return True, "Function signature passed quality checks."

# ============================================================
# IMPORT VALIDATION
# ============================================================

def check_imports(code):

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, "Could not parse code: " + str(e)

    allowed_modules = {
        "json",
        "subprocess",
        "os",
        "sys",
        "time",
        "datetime",
        "math",
        "re",
        "pathlib",
        "shutil",
    }

    for node in tree.body:

        if isinstance(node, ast.Import):

            for alias in node.names:

                module = alias.name.split(".")[0]

                if module not in allowed_modules:
                    return False, (
                        f"Import '{module}' is not allowed."
                    )

        elif isinstance(node, ast.ImportFrom):

            module = (node.module or "").split(".")[0]

            if module not in allowed_modules:
                return False, (
                    f"Import '{module}' is not allowed."
                )

    return True, "Imports passed quality checks."


# ============================================================
# COMMAND SAFETY VALIDATION
# ============================================================

def check_subprocess_usage(code):

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, "Could not parse code: " + str(e)

    for node in ast.walk(tree):

        if not isinstance(node, ast.Call):
            continue

        if not isinstance(node.func, ast.Attribute):
            continue

        if node.func.attr not in {
            "check_call",
            "check_output",
            "run"
        }:
            continue

        if not node.args:
            return False, (
                "subprocess command must provide arguments."
            )

        command = node.args[0]

        if isinstance(command, ast.Constant):
            if isinstance(command.value, str):
                return False, (
                    "subprocess commands must use a list of arguments."
                )

        if not isinstance(command, (ast.List, ast.Tuple)):
            return False, (
                "subprocess commands must use a list or tuple of arguments."
            )

    return True, "Subprocess usage passed safety checks."


# ============================================================
# GENERATE TOOL
# ============================================================

def generate_tool(tool_name, description):

    prompt = f"""
You are Nova's tool developer.

Your job is to create ONE small Python tool.

TOOL NAME:
{tool_name}

CAPABILITY:
{description}

{get_verified_device_capabilities()}

GENERAL RULES:

1. Return ONLY valid Python source code.

2. Do NOT return Markdown.

3. Do NOT use code fences.

4. Do NOT explain the code.

5. The file must import safely.

6. Create exactly ONE main public function.

7. The main function name must be exactly:

   {tool_name}

8. Function arguments:
   - Include ONLY arguments that are genuinely required by the requested capability.
   - Do NOT invent arguments such as 'device', 'phone', or 'context'.
   - The tool automatically operates on the current Android device.
   - If the capability requires no user input, the function MUST have no arguments.
   - Example: battery_status() is correct.
   - Example: set_brightness(level) is correct.

9. ANDROID APP LAUNCHING:
   - When the capability is to open an Android application, NEVER guess or hard-code an Activity class.
   - NEVER use commands such as:
     ["am", "start", "com.example.app/.SomeActivity"]
   - Use the Android launcher intent instead:
     ["am", "start", "-a", "android.intent.action.MAIN",
      "-c", "android.intent.category.LAUNCHER", "-p", "<package.name>"]
   - The package name must correspond to the requested application.
   - Treat the launcher intent as the standard safe method for opening an installed Android application.
   - Do not invent an Activity name.

9. Never use input().

10. Never use eval().

11. Never use exec().

12. Never use shell=True.

13. Never use os.system().

14. Never use os.popen().

15. Never use subprocess.Popen().

16. Never access passwords.

17. Never access API keys.

18. Never access authentication tokens.

19. Never access private personal files.

20. Never execute financial transactions.

21. Never install packages.

22. Never modify Nova's core files.

23. Never delete files unless the requested capability explicitly
    requires deletion.

24. Never execute arbitrary shell commands supplied by a user.

25. Keep the implementation small and focused.

26. When a verified Termux command returns JSON, ALWAYS parse it with
    json.loads(). NEVER use eval() or ast.literal_eval() for command output.

27. If the verified capability specifies an exact command, use that exact
    command. Do not replace it with dumpsys, Android intents, invented APIs,
    or another unverified command.

28. Use only the fields and output format documented by the verified
    capability.

29. Do not add undocumented function parameters. The function signature
    must match the required interface exactly.

26. Handle expected errors safely.

27. Return a dictionary containing:

    success
    verified
    message

28. success=True ONLY when the requested operation completed.

29. verified=True ONLY when the resulting state was actually checked.

30. If an operation fails, return success=False.

31. Never claim success when an underlying operation failed.

32. Do not invent Android APIs or Termux commands.

33. Use only commands supported by the verified device information
    or standard, well-established Termux mechanisms.

34. When using subprocess, ALWAYS use a list of arguments.

CORRECT:

subprocess.check_call(
    ["command", "argument"]
)

INCORRECT:

subprocess.check_call(
    "command argument",
    shell=True
)

Generate ONLY the Python source code.
"""

    try:
        api_key = os.environ["GROQ_API_KEY"]
    except KeyError:
        return {
            "success": False,
            "error": "GROQ_API_KEY environment variable is not set."
        }

    try:

        response = requests.post(
            API_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 1500
            },
            timeout=30
        )

    except requests.RequestException as e:

        return {
            "success": False,
            "error": "Groq request failed: " + str(e)
        }

    if response.status_code != 200:

        return {
            "success": False,
            "error": response.text
        }

    try:

        code = (
            response.json()
            ["choices"][0]
            ["message"]["content"]
            .strip()
        )

    except Exception as e:

        return {
            "success": False,
            "error": "Could not read generated code: " + str(e)
        }

    # Remove Markdown fences if necessary.

    if code.startswith("```"):

        lines = code.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        code = "\n".join(lines).strip()

    # ========================================================
    # VALIDATION PIPELINE
    # ========================================================

    valid, message = validate_generated_code(code)

    if not valid:

        print("\n❌ Generated code failed syntax validation:")
        print(message)

        print("\nGenerated code:")
        print(code)

        return {
            "success": False,
            "error": "Syntax validation failed: " + message
        }

    quality_ok, quality_message = check_generated_code_quality(code)

    if not quality_ok:

        print("\n❌ Generated code failed security checks:")
        print(quality_message)

        print("\nGenerated code:")
        print(code)

        return {
            "success": False,
            "error": quality_message
        }

    signature_ok, signature_message = check_function_signature(
        code,
        tool_name
    )

    if not signature_ok:

        print("\n❌ Generated code failed function checks:")
        print(signature_message)

        print("\nGenerated code:")
        print(code)

        return {
            "success": False,
            "error": signature_message
        }

    imports_ok, imports_message = check_imports(code)

    if not imports_ok:

        print("\n❌ Generated code failed import checks:")
        print(imports_message)

        print("\nGenerated code:")
        print(code)

        return {
            "success": False,
            "error": imports_message
        }

    subprocess_ok, subprocess_message = check_subprocess_usage(code)

    if not subprocess_ok:

        print("\n❌ Generated code failed subprocess checks:")
        print(subprocess_message)

        print("\nGenerated code:")
        print(code)

        return {
            "success": False,
            "error": subprocess_message
        }

    # ========================================================
    # CREATE PROPOSAL
    # ========================================================

    return create_proposal(
        tool_name,
        code
    )


# ============================================================
# MANUAL TEST
# ============================================================

if __name__ == "__main__":

    result = generate_tool(
        "volume_control",
        "Create a tool for controlling Android media volume. "
        "The function MUST be exactly: "
        "def volume_control(action, stream=\"music\", level=None). "
        "The argument names and order MUST NOT be changed. "
        "action MUST support exactly: up, down, set. "
        "For up, increase the current volume by 1. "
        "For down, decrease the current volume by 1. "
        "For set, use the level argument. "
        "The level argument must only be used for the set action. "
        "Invalid actions must return a safe error result. "
        "Use the verified Termux volume capability. "
        "Verify that the requested volume actually changed. "
        "Never assume volumes[0] is the requested stream; find the item whose "
        "'stream' field matches the stream argument before reading or verifying its volume. "
        "Do not create another parameter such as new_level. "
        "Return a dictionary containing success, verified, and message."
    )

    print(result)
