"""Install Nova's generic semantic navigation helper into the planner.

The change is provider-agnostic and app-agnostic. It adds one generic tool that
can search the live Android hierarchy, scroll when necessary, and activate a
semantic target. No Settings/Android screen names are hard-coded.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "nova_agent.py"


def main():
    if not TARGET.exists():
        raise SystemExit(f"Missing {TARGET}")

    text = TARGET.read_text(encoding="utf-8")
    original = text

    # Keep the local multi-provider router if this checkout has already been
    # integrated with it. Never overwrite that provider architecture here.

    # Add the generic tool to the planner's allowed tool set.
    if '    "navigate_android_to",\n' not in text:
        marker = '    "scroll_android",\n'
        if marker not in text:
            raise SystemExit("Could not find Nova's AGENT_TOOLS block.")
        text = text.replace(marker, marker + '    "navigate_android_to",\n', 1)

    # Strengthen the generic planner guidance without adding an app-specific
    # destination or procedure.
    rule = (
        "15. For a named destination that may be off-screen, prefer the generic "
        "navigate_android_to primitive. It searches the live hierarchy and can "
        "scroll before activating a semantic match. Do not use Back just because "
        "a target is not currently visible."
    )
    if "prefer the generic navigate_android_to primitive" not in text:
        marker = "14. Never relaunch an app merely because Termux is where Nova is running.\n"
        if marker not in text:
            raise SystemExit("Could not find Nova's generic planner rules.")
        text = text.replace(marker, marker + rule + "\n", 1)

    primitive_line = (
        "observe_android, find_android_app, launch_android_app, click_node,\n"
        "click_text, type_text, back_android, scroll_android."
    )
    primitive_new = (
        "observe_android, find_android_app, launch_android_app, click_node,\n"
        "click_text, type_text, back_android, scroll_android, navigate_android_to."
    )
    if primitive_line in text:
        text = text.replace(primitive_line, primitive_new, 1)

    if text == original:
        print("ℹ️ Generic semantic navigation is already installed.")
        return

    TARGET.write_text(text, encoding="utf-8")
    print("✅ Installed Nova's generic semantic Android navigation helper.")
    print("   Named targets can now be searched, scrolled into view, and activated")
    print("   from the live UI hierarchy without app-specific hard-coding.")


if __name__ == "__main__":
    main()
