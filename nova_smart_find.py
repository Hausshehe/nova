from pathlib import Path

p = Path("android/src/com/infoney/nova/NovaAccessibilityService.java")
text = p.read_text()

start = text.find("    private AccessibilityNodeInfo findMatchingNode(")
end = text.find("\n    private boolean clickNode(", start)

if start == -1:
    raise SystemExit("ERROR: findMatchingNode start not found")

if end == -1:
    raise SystemExit("ERROR: clickNode boundary not found")

new_methods = r'''    private AccessibilityNodeInfo findMatchingNode(
            AccessibilityNodeInfo node,
            String target) {

        if (node == null) {
            return null;
        }

        String wanted = target.trim().toLowerCase();

        CharSequence text = node.getText();
        CharSequence description = node.getContentDescription();

        String textValue =
                text != null ? text.toString().trim() : "";

        String descValue =
                description != null ? description.toString().trim() : "";

        String textLower = textValue.toLowerCase();
        String descLower = descValue.toLowerCase();

        if (wanted.equals(textLower)) {

            Log.i(
                    TAG,
                    "MATCH: exact text=\"" + textValue + "\""
            );

            AccessibilityNodeInfo control =
                    findRelatedClickableControl(node);

            if (control != null) {
                Log.i(
                        TAG,
                        "SMART_MATCH: related control="
                                + control.getClassName()
                );
                return control;
            }

            return node;
        }

        if (wanted.equals(descLower)) {

            Log.i(
                    TAG,
                    "MATCH: exact description=\"" + descValue + "\""
            );

            AccessibilityNodeInfo control =
                    findRelatedClickableControl(node);

            if (control != null) {
                return control;
            }

            return node;
        }

        if (!textLower.isEmpty()
                && textLower.contains(wanted)) {

            Log.i(
                    TAG,
                    "MATCH: text contains target=\""
                            + textValue + "\""
            );

            AccessibilityNodeInfo control =
                    findRelatedClickableControl(node);

            if (control != null) {
                return control;
            }

            return node;
        }

        if (!descLower.isEmpty()
                && descLower.contains(wanted)) {

            Log.i(
                    TAG,
                    "MATCH: description contains target=\""
                            + descValue + "\""
            );

            AccessibilityNodeInfo control =
                    findRelatedClickableControl(node);

            if (control != null) {
                return control;
            }

            return node;
        }

        for (int i = 0;
                i < node.getChildCount();
                i++) {

            AccessibilityNodeInfo child =
                    node.getChild(i);

            AccessibilityNodeInfo found =
                    findMatchingNode(child, target);

            if (found != null) {
                return found;
            }
        }

        return null;
    }


    private AccessibilityNodeInfo findRelatedClickableControl(
            AccessibilityNodeInfo node) {

        if (node == null) {
            return null;
        }

        if (isPreferredClickableControl(node)) {
            return node;
        }

        AccessibilityNodeInfo current =
                node.getParent();

        int depth = 0;

        while (current != null && depth < 5) {

            Log.i(
                    TAG,
                    "SMART_CONTROL: ancestor depth="
                            + depth
                            + " class="
                            + current.getClassName()
                            + " clickable="
                            + current.isClickable()
            );

            AccessibilityNodeInfo control =
                    findPreferredControlInSubtree(current);

            if (control != null) {
                return control;
            }

            if (current.isEnabled()
                    && current.isClickable()) {

                return current;
            }

            AccessibilityNodeInfo next =
                    current.getParent();

            current.recycle();
            current = next;
            depth++;
        }

        return null;
    }


    private AccessibilityNodeInfo findPreferredControlInSubtree(
            AccessibilityNodeInfo node) {

        if (node == null) {
            return null;
        }

        if (isPreferredClickableControl(node)) {
            return node;
        }

        for (int i = 0;
                i < node.getChildCount();
                i++) {

            AccessibilityNodeInfo child =
                    node.getChild(i);

            AccessibilityNodeInfo found =
                    findPreferredControlInSubtree(child);

            if (found != null) {
                return found;
            }
        }

        if (node.isEnabled()
                && node.isClickable()) {

            return node;
        }

        return null;
    }


    private boolean isPreferredClickableControl(
            AccessibilityNodeInfo node) {

        if (node == null
                || !node.isEnabled()
                || !node.isClickable()) {

            return false;
        }

        CharSequence className =
                node.getClassName();

        if (className == null) {
            return false;
        }

        String classValue =
                className.toString();

        return classValue.equals("android.widget.Switch")
                || classValue.equals("android.widget.ToggleButton")
                || classValue.equals("android.widget.CheckBox")
                || classValue.equals("android.widget.RadioButton")
                || node.isCheckable();
    }

'''

text = text[:start] + new_methods + text[end:]

p.write_text(text)

print("SMART NODE DISCOVERY INSTALLED")
