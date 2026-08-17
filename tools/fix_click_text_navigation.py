from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "android/src/com/infoney/nova/NovaAccessibilityService.java"

OLD = '''    public boolean clickText(String target) {
        if (target == null || target.trim().isEmpty()) {
            Log.w(TAG, "CLICK_TEXT: empty target");
            return false;
        }
        target = target.trim();
        Log.i(TAG, "CLICK_TEXT: searching for: " + target);
        AccessibilityNodeInfo node = findTargetNodeInAllWindows(target);
        if (node == null) {
            Log.w(TAG, "CLICK_TEXT: target node not found: " + target);
            return false;
        }
        Log.i(TAG, "CLICK_TEXT: target found, attempting click: " + target);
        boolean result = clickNode(node, target);
        Log.i(TAG, "CLICK_TEXT result=" + result + " target=" + target);
        return result;
    }
'''

NEW = '''    public boolean clickText(String target) {
        if (target == null || target.trim().isEmpty()) {
            Log.w(TAG, "CLICK_TEXT: empty target");
            return false;
        }
        target = target.trim();
        Log.i(TAG, "CLICK_TEXT: searching for: " + target);

        // Do not make the planner guess when a target is just below the
        // visible viewport. Search first, then scroll the active UI and retry
        // a few times. This is especially important for Settings RecyclerViews.
        final int maxAttempts = 6;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            AccessibilityNodeInfo node = findTargetNodeInAllWindows(target);
            if (node != null) {
                Log.i(TAG, "CLICK_TEXT: target found on attempt " + attempt + ", attempting click: " + target);
                boolean result = clickNode(node, target);
                Log.i(TAG, "CLICK_TEXT result=" + result + " target=" + target + " attempt=" + attempt);
                if (result) return true;
            } else {
                Log.i(TAG, "CLICK_TEXT: target not currently visible, attempt=" + attempt + "/" + maxAttempts);
            }

            if (attempt < maxAttempts) {
                boolean scrolled = scrollActiveWindowForward();
                Log.i(TAG, "CLICK_TEXT: auto-scroll forward=" + scrolled + " before retry=" + (attempt + 1));
                if (!scrolled) break;
                try {
                    Thread.sleep(350);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }

        Log.w(TAG, "CLICK_TEXT: target could not be clicked after auto-scroll retries: " + target);
        return false;
    }

    private boolean scrollActiveWindowForward() {
        try {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root == null) return false;
            boolean result = scrollNodeForward(root);
            root.recycle();
            return result;
        } catch (Exception e) {
            Log.e(TAG, "CLICK_TEXT: auto-scroll failed", e);
            return false;
        }
    }

    private boolean scrollNodeForward(AccessibilityNodeInfo node) {
        if (node == null) return false;

        if (node.isScrollable() && node.isEnabled()) {
            boolean moved = node.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
            Log.i(TAG, "CLICK_TEXT: scroll container=" + node.getClassName() + " moved=" + moved);
            if (moved) return true;
        }

        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child == null) continue;
            boolean moved = scrollNodeForward(child);
            child.recycle();
            if (moved) return true;
        }
        return false;
    }
'''

source = PATH.read_text()
if NEW in source:
    print("click_text navigation fix already installed.")
    raise SystemExit(0)

if OLD not in source:
    raise SystemExit("Could not locate clickText() in NovaAccessibilityService.java")

PATH.write_text(source.replace(OLD, NEW, 1))
print("Updated clickText() with deterministic auto-scroll/retry navigation.")
