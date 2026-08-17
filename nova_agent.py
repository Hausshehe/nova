"""Nova's goal-driven Android agent loop."""

import inspect
import json
import os
import re
import time

import requests

from ai_router import call_ai
from tools.executor import execute_tool
from tools.registry import discover_tools
from tools.navigate_android_to import navigate_android_to


API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
MAX_STEPS = 16
MAX_GROQ_RETRIES = 4
GROQ_BACKOFF_SECONDS = 1.5
MAX_GROQ_RETRY_DELAY = 15.0
MAX_HISTORY_PAIRS = 3
SIMPLE_OPEN_VERIFY_ATTEMPTS = 6
SIMPLE_OPEN_VERIFY_DELAY = 0.75
SIMPLE_OPEN_PATH_SCROLL_ATTEMPTS = 8
SIMPLE_OPEN_PATH_SCROLL_DELAY = 0.6

AGENT_TOOLS = {
    "observe_android",
    "find_android_app",
    "launch_android_app",
    "click_text",
    "click_node",
    "type_text",
    "back_android",
    "scroll_android",
}


def _normalize_ui_text(value):
    """Normalize UI labels for semantic, coordinate-free matching."""
    text = str(value or "").strip().lower()
    text = text.replace("‑", "-").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9&+.#' -]", "", text)
    return text.strip()


def _simple_open_goal(goal):
    """Recognize only the narrow generic 'open/launch/start app' goal."""
    normalized = re.sub(r"\s+", " ", str(goal or "").strip().lower())
    match = re.fullmatch(r"(?:open|launch|start)\s+(.+?)(?:\s+app)?", normalized)
    return match.group(1).strip() if match else ""


def _simple_open_path_goal(goal):
    """Recognize a generic multi-stage open goal without naming app-specific targets."""
    normalized = re.sub(r"\s+", " ", str(goal or "").strip().lower())
    match = re.fullmatch(
        r"(?:open|launch|start)\s+(.+?)\s+(?:and|then)\s+(?:open|launch|start)\s+(.+?)",
        normalized,
    )
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _observe_directly():
    """Observe without spending another planner/AI turn."""
    return _unwrap_tool_result(execute_tool("observe_android", "observe_android"))


def _foreground_from_observation(verification):
    """Extract the authoritative foreground package from an observation."""
    if not isinstance(verification, dict):
        return ""
    foreground = verification.get("foreground_package", "")
    if not foreground:
        foreground = (verification.get("state") or {}).get("foreground_package", "")
    return foreground or ""


def _visible_text_from_observation(verification):
    if not isinstance(verification, dict):
        return []
    state = verification.get("state") or {}
    return state.get("visible_text") or []


def _find_visible_target(verification, target):
    """Find the best current visible label matching the user's target semantically."""
    wanted = _normalize_ui_text(target)
    if not wanted:
        return ""

    candidates = _visible_text_from_observation(verification)
    normalized_candidates = [
        (str(candidate), _normalize_ui_text(candidate))
        for candidate in candidates
        if str(candidate).strip()
    ]

    for original, normalized in normalized_candidates:
        if normalized == wanted:
            return original

    for original, normalized in normalized_candidates:
        if wanted in normalized or normalized in wanted:
            return original

    return ""


def _run_simple_open_goal(app_name):
    """Handle the generic open-app primitive locally, without planner tokens.

    Do app discovery before the initial UI observation. This avoids spending the
    entire observation timeout before Nova has even attempted the requested
    launch, which is especially important when uiautomator is temporarily slow
    during an Activity transition. No app-specific package or coordinate is
    encoded here.
    """
    discovery = _unwrap_tool_result(
        execute_tool("find_android_app", "find_android_app", app_name=app_name)
    )
    packages = discovery.get("packages") or [] if isinstance(discovery, dict) else []
    if not packages:
        return {
            "success": False,
            "verified": bool(discovery.get("verified")) if isinstance(discovery, dict) else False,
            "message": f"I couldn't find an installed app matching '{app_name}'.",
            "steps": 0,
        }

    package = packages[0]

    # If the requested package is already foreground, avoid relaunching it.
    # This uses the generic foreground query only; it does not assume any app.
    verification = _observe_directly()
    foreground = _foreground_from_observation(verification)
    if verification.get("success") and foreground == package:
        return {
            "success": True,
            "verified": True,
            "message": f"{app_name} is already open and in the foreground.",
            "steps": 0,
        }

    launch = _unwrap_tool_result(
        execute_tool("launch_android_app", "launch_android_app", package=package)
    )
    if not launch.get("success"):
        return {
            "success": False,
            "verified": False,
            "message": launch.get("message", "The app could not be launched."),
            "steps": 0,
        }

    for attempt in range(1, SIMPLE_OPEN_VERIFY_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(SIMPLE_OPEN_VERIFY_DELAY)
        verification = _observe_directly()
        foreground = _foreground_from_observation(verification)
        if verification.get("success") and foreground == package:
            return {
                "success": True,
                "verified": True,
                "message": f"{app_name} is open and verified in the foreground.",
                "steps": 0,
            }

    return {
        "success": False,
        "verified": False,
        "message": (
            f"I launched {app_name}, but after waiting for the app to become "
            f"foreground, verification still shows {foreground or 'another app'}."
        ),
        "steps": 0,
    }


def _run_simple_open_path_goal(app_name, target):
    """Open an app, then navigate to a human-named destination adaptively."""
    opened = _run_simple_open_goal(app_name)
    if not opened.get("success"):
        return opened

    result = navigate_android_to(
        target,
        max_scrolls=SIMPLE_OPEN_PATH_SCROLL_ATTEMPTS,
        direction="down",
    )

    if not isinstance(result, dict):
        return {
            "success": False,
            "verified": False,
            "message": f"{app_name} opened, but navigation returned an invalid result.",
            "steps": 1,
        }

    if result.get("success") and result.get("verified"):
        return {
            "success": True,
            "verified": True,
            "message": (
                f"Opened {target} inside {app_name} using adaptive semantic navigation."
            ),
            "steps": int(result.get("scrolls", 0)) + 2,
        }

    return {
        "success": False,
        "verified": bool(result.get("verified")),
        "message": result.get(
            "message",
            f"{app_name} is open, but Nova could not locate '{target}'.",
        ),
        "steps": int(result.get("scrolls", 0)) + 1,
    }


def _compact_history(messages):
    """Keep only recent action/observation pairs; current state is ground truth."""
    if len(messages) <= 2 + (MAX_HISTORY_PAIRS * 2):
        return messages
    recent = messages[-(MAX_HISTORY_PAIRS * 2):]
    return messages[:2] + recent


def run_agent(goal):
    """Run Nova's adaptive goal/action/observation loop for one goal."""
    goal = str(goal or "").strip()
    if not goal:
        return {"success": False, "message": "Goal cannot be empty."}

    simple_open_path = _simple_open_path_goal(goal)
    if simple_open_path:
        return _run_simple_open_path_goal(*simple_open_path)

    simple_open_app = _simple_open_goal(goal)
    if simple_open_app:
        return _run_simple_open_goal(simple_open_app)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Accomplish this goal on the Android phone:\n" + goal},
    ]

    action_seen = False
    observed_after_action = False

    for step in range(1, MAX_STEPS + 1):
        messages = _compact_history(messages)
        message = call_ai(messages, build_agent_tool_definitions())
        messages.append(message)
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            answer = (message.get("content") or "").strip()
            if action_seen and not observed_after_action:
                messages.append({"role": "user", "content": "Observe the current UI and verify the goal before concluding."})
                continue
            return {
                "success": True,
                "verified": bool(observed_after_action),
                "message": answer or "Goal completed.",
                "steps": step,
            }

        action_seen = True
        observed_after_action = False
        for tool_call in tool_calls:
            tool_result = _execute_agent_tool_call(tool_call)
            messages.append(tool_result)
            try:
                parsed = json.loads(tool_result.get("content", "{}"))
            except (TypeError, ValueError):
                parsed = {}
            if tool_call.get("function", {}).get("name") == "observe_android":
                observed_after_action = True

    return {
        "success": False,
        "verified": observed_after_action,
        "message": f"Nova reached the maximum of {MAX_STEPS} planning steps without completing the goal.",
        "steps": MAX_STEPS,
    }
