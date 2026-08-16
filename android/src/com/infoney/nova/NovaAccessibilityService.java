package com.infoney.nova;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.provider.Settings;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class NovaAccessibilityService extends AccessibilityService {

    private static final String TAG = "NovaAccessibility";

    public static NovaAccessibilityService instance;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;

        Log.i(TAG, "Nova Accessibility Service connected.");
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {

        if (event == null) {
            return;
        }

        AccessibilityNodeInfo root =
                getRootInActiveWindow();

        if (root == null) {
            return;
        }

        String packageName =
                event.getPackageName() != null
                        ? event.getPackageName().toString()
                        : "unknown";

        Log.i(TAG, "SCREEN: " + packageName);

        Set<String> seen = new HashSet<>();

        scanNode(root, seen);
    }

    @Override
    public void onInterrupt() {
        Log.w(TAG, "Accessibility service interrupted.");
    }

    private void scanNode(
            AccessibilityNodeInfo node,
            Set<String> seen) {

        if (node == null) {
            return;
        }

        CharSequence text =
                node.getText();

        CharSequence description =
                node.getContentDescription();

        String value = null;

        if (text != null
                && text.length() > 0) {

            value = text.toString();

        } else if (description != null
                && description.length() > 0) {

            value = description.toString();
        }

        if (value != null) {

            String key =
                    value + "|" + node.isClickable();

            if (!seen.contains(key)) {

                seen.add(key);

                if (node.isClickable()) {

                    Log.i(
                            TAG,
                            "CLICKABLE: " + value
                    );

                } else {

                    Log.i(
                            TAG,
                            "TEXT: " + value
                    );
                }
            }
        }

        for (int i = 0;
                i < node.getChildCount();
                i++) {

            scanNode(
                    node.getChild(i),
                    seen
            );
        }
    }

    public static boolean handleClickText(
            String text) {

        if (instance == null) {

            Log.w(
                    TAG,
                    "CLICK_TEXT: service instance is null"
            );

            return false;
        }

        return instance.clickText(text);
    }

    public boolean clickText(String target) {

        if (target == null
                || target.trim().isEmpty()) {

            Log.w(
                    TAG,
                    "CLICK_TEXT: empty target"
            );

            return false;
        }

        target = target.trim();

        Log.i(
                TAG,
                "CLICK_TEXT: searching for: "
                        + target
        );

        AccessibilityNodeInfo node =
                findTargetNodeInAllWindows(target);

        if (node == null) {

            Log.w(
                    TAG,
                    "CLICK_TEXT: target node not found: "
                            + target
            );

            return false;
        }

        Log.i(
                TAG,
                "CLICK_TEXT: target found, attempting click: "
                        + target
        );

        boolean result =
                clickNode(node, target);

        Log.i(
                TAG,
                "CLICK_TEXT result="
                        + result
                        + " target="
                        + target
        );

        return result;
    }

    private AccessibilityNodeInfo findSwitchNodeInAllWindows() {

        Log.i(
                TAG,
                "SWITCH_SEARCH: searching for Android Switch"
        );

        try {

            AccessibilityNodeInfo root =
                    getRootInActiveWindow();

            if (root != null) {

                AccessibilityNodeInfo found =
                        findSwitchNode(root);

                if (found != null) {

                    Log.i(
                            TAG,
                            "SWITCH_SEARCH: switch FOUND in active root"
                    );

                    return found;
                }
            }

        } catch (Exception e) {

            Log.e(
                    TAG,
                    "SWITCH_SEARCH: active root failed",
                    e
            );
        }

        try {

            List<AccessibilityWindowInfo> windows =
                    getWindows();

            if (windows != null) {

                for (AccessibilityWindowInfo window : windows) {

                    if (window == null) {
                        continue;
                    }

                    AccessibilityNodeInfo root =
                            window.getRoot();

                    if (root == null) {
                        continue;
                    }

                    AccessibilityNodeInfo found =
                            findSwitchNode(root);

                    if (found != null) {

                        Log.i(
                                TAG,
                                "SWITCH_SEARCH: switch FOUND in window"
                        );

                        return found;
                    }
                }
            }

        } catch (Exception e) {

            Log.e(
                    TAG,
                    "SWITCH_SEARCH: getWindows failed",
                    e
            );
        }

        Log.w(
                TAG,
                "SWITCH_SEARCH: switch not found"
        );

        return null;
    }

    private AccessibilityNodeInfo findSwitchNode(
            AccessibilityNodeInfo node) {

        if (node == null) {
            return null;
        }

        CharSequence className =
                node.getClassName();

        CharSequence resourceId =
                node.getViewIdResourceName();

        if (className != null
                && "android.widget.Switch".equals(
                        className.toString())) {

            Log.i(
                    TAG,
                    "SWITCH_MATCH: class="
                            + className
                            + " resourceId="
                            + resourceId
                            + " checked="
                            + node.isChecked()
                            + " clickable="
                            + node.isClickable()
                            + " enabled="
                            + node.isEnabled()
            );

            return node;
        }

        for (int i = 0;
                i < node.getChildCount();
                i++) {

            AccessibilityNodeInfo child =
                    node.getChild(i);

            AccessibilityNodeInfo found =
                    findSwitchNode(child);

            if (found != null) {
                return found;
            }
        }

        return null;
    }

    public boolean clickSwitch() {

        Log.i(
                TAG,
                "CLICK_SWITCH: searching for switch"
        );

        AccessibilityNodeInfo node =
                findSwitchNodeInAllWindows();

        if (node == null) {

            Log.w(
                    TAG,
                    "CLICK_SWITCH: switch not found"
            );

            return false;
        }

        Log.i(
                TAG,
                "CLICK_SWITCH: found switch checked="
                        + node.isChecked()
                        + " clickable="
                        + node.isClickable()
                        + " enabled="
                        + node.isEnabled()
        );

        boolean result =
                clickNode(
                        node,
                        "android.widget.Switch"
                );

        Log.i(
                TAG,
                "CLICK_SWITCH result="
                        + result
        );

        return result;
    }

    public boolean clickElement(String target) {
        if (target == null || target.trim().isEmpty()) {
            Log.w(TAG, "CLICK_ELEMENT: empty target");
            return false;
        }

        target = target.trim();
        Log.i(TAG, "CLICK_ELEMENT: searching for: " + target);

        AccessibilityNodeInfo node = findTargetNodeInAllWindows(target);

        if (node == null) {
            Log.w(TAG, "CLICK_ELEMENT: target not found: " + target);
            return false;
        }

        Log.i(TAG, "CLICK_ELEMENT: found target=" + target
                + " class=" + node.getClassName()
                + " clickable=" + node.isClickable()
                + " enabled=" + node.isEnabled()
                + " actions=" + node.getActionList());

        boolean result = clickNode(node, target);

        Log.i(TAG, "CLICK_ELEMENT result=" + result
                + " target=" + target);

        return result;
    }

    private AccessibilityNodeInfo findTargetNodeInAllWindows(
            String target) {

        Log.i(
                TAG,
                "WINDOW_SEARCH: searching for: "
                        + target
        );

        /*
         * METHOD 1
         *
         * Search the current active root FIRST.
         *
         * This is important because getWindows() can
         * temporarily return zero windows on some devices.
         */

        try {

            AccessibilityNodeInfo activeRoot =
                    getRootInActiveWindow();

            if (activeRoot != null) {

                CharSequence packageName =
                        activeRoot.getPackageName();

                Log.i(
                        TAG,
                        "WINDOW_SEARCH: active root package="
                                + (packageName != null
                                ? packageName.toString()
                                : "unknown")
                );

                AccessibilityNodeInfo found =
                        findMatchingNode(
                                activeRoot,
                                target
                        );

                if (found != null) {

                    Log.i(
                            TAG,
                            "WINDOW_SEARCH: FOUND in active root target="
                                    + target
                    );

                    return found;
                }

            } else {

                Log.w(
                        TAG,
                        "WINDOW_SEARCH: active root is null"
                );
            }

        } catch (Exception e) {

            Log.e(
                    TAG,
                    "WINDOW_SEARCH: active root failed",
                    e
            );
        }

        /*
         * METHOD 2
         *
         * Search all accessibility windows.
         */

        try {

            List<AccessibilityWindowInfo> windows =
                    getWindows();

            if (windows != null) {

                Log.i(
                        TAG,
                        "WINDOW_SEARCH: getWindows() returned "
                                + windows.size()
                                + " windows"
                );

                for (AccessibilityWindowInfo window
                        : windows) {

                    if (window == null) {
                        continue;
                    }

                    AccessibilityNodeInfo root =
                            window.getRoot();

                    if (root == null) {
                        continue;
                    }

                    CharSequence packageName =
                            root.getPackageName();

                    Log.i(
                            TAG,
                            "WINDOW_SEARCH: package="
                                    + (packageName != null
                                    ? packageName.toString()
                                    : "unknown")
                                    + " type="
                                    + window.getType()
                                    + " active="
                                    + window.isActive()
                                    + " focused="
                                    + window.isFocused()
                    );

                    AccessibilityNodeInfo found =
                            findMatchingNode(
                                    root,
                                    target
                            );

                    if (found != null) {

                        Log.i(
                                TAG,
                                "WINDOW_SEARCH: FOUND target="
                                        + target
                                        + " package="
                                        + (packageName != null
                                        ? packageName.toString()
                                        : "unknown")
                        );

                        return found;
                    }
                }
            }

        } catch (Exception e) {

            Log.e(
                    TAG,
                    "WINDOW_SEARCH: getWindows failed",
                    e
            );
        }

        Log.w(
                TAG,
                "WINDOW_SEARCH: target not found="
                        + target
        );

        return null;
    }

    private AccessibilityNodeInfo findMatchingNode(
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


    private boolean clickNode(
            AccessibilityNodeInfo node,
            String target) {

        if (node == null) {
            return false;
        }

        Log.i(
                TAG,
                "CLICK_NODE: target="
                        + target
                        + " class="
                        + node.getClassName()
                        + " text="
                        + node.getText()
                        + " description="
                        + node.getContentDescription()
                        + " clickable="
                        + node.isClickable()
                        + " enabled="
                        + node.isEnabled()
                        + " checked="
                        + node.isChecked()
                        + " actions="
                        + node.getActionList()
        );

        /*
         * METHOD 1
         *
         * Direct ACTION_CLICK.
         */
        if (node.isEnabled() && node.isClickable()) {

            boolean clicked =
                    node.performAction(
                            AccessibilityNodeInfo.ACTION_CLICK
                    );

            Log.i(
                    TAG,
                    "CLICK_NODE: direct ACTION_CLICK="
                            + clicked
            );

            if (clicked) {
                return true;
            }
        }

        /*
         * METHOD 2
         *
         * Try a clickable parent.
         */
        AccessibilityNodeInfo parent =
                node.getParent();

        int depth = 0;

        while (parent != null) {

            Log.i(
                    TAG,
                    "CLICK_NODE: parent depth="
                            + depth
                            + " class="
                            + parent.getClassName()
                            + " clickable="
                            + parent.isClickable()
                            + " enabled="
                            + parent.isEnabled()
                            + " actions="
                            + parent.getActionList()
            );

            if (parent.isEnabled()
                    && parent.isClickable()) {

                boolean clicked =
                        parent.performAction(
                                AccessibilityNodeInfo.ACTION_CLICK
                        );

                Log.i(
                        TAG,
                        "CLICK_NODE: parent ACTION_CLICK="
                                + clicked
                                + " depth="
                                + depth
                );

                if (clicked) {
                    parent.recycle();
                    return true;
                }
            }

            AccessibilityNodeInfo next =
                    parent.getParent();

            parent.recycle();
            parent = next;
            depth++;
        }

        /*
         * METHOD 3
         *
         * Physical gesture fallback.
         */
        android.graphics.Rect bounds =
                new android.graphics.Rect();

        node.getBoundsInScreen(bounds);

        Log.i(
                TAG,
                "CLICK_NODE: bounds="
                        + bounds
        );

        if (bounds.isEmpty()) {

            Log.w(
                    TAG,
                    "CLICK_NODE: empty bounds target="
                            + target
            );

            return false;
        }

        float x = bounds.centerX();
        float y = bounds.centerY();

        Log.i(
                TAG,
                "CLICK_NODE: gesture tap x="
                        + x
                        + " y="
                        + y
        );

        android.graphics.Path path =
                new android.graphics.Path();

        path.moveTo(x, y);

        android.accessibilityservice.GestureDescription.StrokeDescription stroke =
                new android.accessibilityservice.GestureDescription.StrokeDescription(
                        path,
                        0,
                        100
                );

        android.accessibilityservice.GestureDescription gesture =
                new android.accessibilityservice.GestureDescription.Builder()
                        .addStroke(stroke)
                        .build();

        boolean dispatched =
                dispatchGesture(
                        gesture,
                        new android.accessibilityservice.AccessibilityService.GestureResultCallback() {

                            @Override
                            public void onCompleted(
                                    android.accessibilityservice.GestureDescription gestureDescription) {

                                Log.i(
                                        TAG,
                                        "CLICK_NODE: gesture COMPLETED target="
                                                + target
                                );
                            }

                            @Override
                            public void onCancelled(
                                    android.accessibilityservice.GestureDescription gestureDescription) {

                                Log.w(
                                        TAG,
                                        "CLICK_NODE: gesture CANCELLED target="
                                                + target
                                );
                            }
                        },
                        null
                );

        Log.i(
                TAG,
                "CLICK_NODE: gesture dispatched="
                        + dispatched
        );

        return dispatched;
    }

    public boolean openBluetoothAndClick() {
        Log.i(
            TAG,
            "OPEN_BLUETOOTH: launching Bluetooth settings"
        );

        boolean opened = openBluetoothSettings();

        if (!opened) {
            Log.e(
                TAG,
                "OPEN_BLUETOOTH: failed to launch Bluetooth settings"
            );
            return false;
        }

        Log.i(
            TAG,
            "OPEN_BLUETOOTH: Bluetooth Settings launch requested successfully"
        );

        return true;
    }

    public boolean openBluetoothSettings() {

        try {

            Log.i(
                    TAG,
                    "OPEN_BLUETOOTH: launching Bluetooth Settings"
            );

            Intent intent =
                    new Intent(
                            Settings.ACTION_BLUETOOTH_SETTINGS
                    );

            intent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK
            );

            startActivity(intent);

            return true;

        } catch (Exception e) {

            Log.e(
                    TAG,
                    "OPEN_BLUETOOTH: failed",
                    e
            );

            return false;
        }
    }
}
