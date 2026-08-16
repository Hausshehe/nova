from pathlib import Path
import re

PATH = Path("nova_agent.py")
text = PATH.read_text(encoding="utf-8")
original = text

# Groq Free/standard orgs may reject this optional tier. Remove it wherever it
# appears in the payload rather than depending on one exact surrounding block.
text = re.sub(r'^\s*"service_tier"\s*:\s*"auto",?\s*\n', '', text, count=1, flags=re.MULTILINE)

# Reduce stale planner history. This preserves adaptive reasoning while lowering
# the amount of old action/observation context sent to Groq.
text = re.sub(r'^MAX_HISTORY_PAIRS\s*=\s*\d+', 'MAX_HISTORY_PAIRS = 2', text, count=1, flags=re.MULTILINE)

# Add a generic navigation rule without depending on the exact wording of the
# surrounding prompt. If the rule is already present, leave it alone.
navigation_rule = (
    "10. When the goal names a destination screen or setting, reaching the parent "
    "app is not enough: continue navigating until that destination is visible "
    "or there is reliable evidence it cannot be reached. If a named destination "
    "is not visible in a scrollable list, prefer scrolling and observing again "
    "before going back. Do not use Back merely because the target is below the "
    "current viewport. When it becomes visible, activate it using its current "
    "semantic node and observe the resulting screen."
)
if "Do not use Back merely because the target is below the current viewport." not in text:
    rule_pattern = r'(\n9\.\s+Use back and scrolling when needed\.)(\n10\.)'
    updated, count = re.subn(
        rule_pattern,
        r'\1\n' + navigation_rule + r'\n11.',
        text,
        count=1,
    )
    if count == 0:
        # Fall back to inserting before the destructive-action rule, regardless
        # of its exact numbering/line wrapping.
        marker = "For destructive, privacy-sensitive, financial, account, or otherwise"
        if marker not in text:
            raise SystemExit("Could not locate the generic safety/navigation rules; no changes made.")
        updated = text.replace(
            marker,
            navigation_rule + "\n" + marker,
            1,
        )
    text = updated

# Do not send the formatted human-readable summary when the structured state is
# already present. This removes duplicated visible-text/interactive information.
text = re.sub(
    r'(\s+"verified": bool\(result\.get\("verified"\)\),)\n\s+"summary": result\.get\("summary", ""\),\n',
    r'\1\n',
    text,
    count=1,
)

if text == original:
    print("Nova's planner already contains these improvements; no changes were necessary.")
else:
    PATH.write_text(text, encoding="utf-8")
    print("Updated Nova's adaptive Android planner: lower stale-history token use, stronger generic navigation, compact observations, and no unsupported Groq service_tier.")
