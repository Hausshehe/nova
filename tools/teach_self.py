import os
import sys

BASE_DIR = "/data/data/com.termux/files/home/infoney"

sys.path.insert(0, BASE_DIR)


def teach_self(tool_name, description):
    try:
        from tools.ai_builder import generate_tool
        from tools.proposal_tester import test_proposal

        # -------------------------------------------------
        # 1. Generate proposal
        # -------------------------------------------------
        generated = generate_tool(
            tool_name,
            description
        )

        if not generated.get("success"):
            return {
                "success": False,
                "stage": "generation",
                "message": generated.get(
                    "error",
                    "Tool generation failed."
                )
            }

        # -------------------------------------------------
        # 2. Validate proposal
        # -------------------------------------------------
        tested = test_proposal(tool_name)

        if not tested.get("success"):
            return {
                "success": False,
                "stage": "validation",
                "tool": tool_name,
                "message": tested.get(
                    "error",
                    "Proposal validation failed."
                )
            }

        # -------------------------------------------------
        # 3. Stop before installation
        # -------------------------------------------------
        return {
            "success": True,
            "stage": "approval_required",
            "tool": tool_name,
            "message": (
                f"Tool '{tool_name}' was generated and "
                "passed the proposal tests. "
                "User approval is required before installation."
            )
        }

    except Exception as e:
        return {
            "success": False,
            "stage": "teach_self",
            "message": str(e)
        }
