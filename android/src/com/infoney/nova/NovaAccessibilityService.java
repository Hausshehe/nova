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
        if (event == null) return;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        String packageName = event.getPackageName() != null ? event.getPackageName().toString() : "unknown";
        Log.i(TAG, "SCREEN: " + packageName);
        Set<String> seen = new HashSet<>();
        scanNode(root, seen);
    }

    @Override
    public void onInterrupt() {
        Log.w(TAG, "Accessibility service interrupted.");
    }

    private void scanNode(AccessibilityNodeInfo node, Set<String> seen) {
        if (node == null) return;
        CharSequence text = node.getText();
        CharSequence description = node.getContentDescription();
        String value = null;
        if (text != null && text.length() > 0) value = text.toString();
        else if (description != null && description.length() > 0) value = description.toString();
        if (value != null) {
            String key = value + "|" + node.isClickable();
            if (!seen.contains(key)) {
                seen.add(key);
                Log.i(TAG, (node.isClickable() ? "CLICKABLE: " : "TEXT: ") + value);
            }
        }
        for (int i = 0; i < node.getChildCount(); i++) scanNode(node.getChild(i), seen);
    }

    public static boolean handleClickText(String text) {
        if (instance == null) {
            Log.w(TAG, "CLICK_TEXT: service instance is null");
            return false;
        }
        return instance.clickText(text);
    }

    public boolean clickText(String target) {
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

    private AccessibilityNodeInfo findSwitchNodeInAllWindows() {
        try {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root != null) {
                AccessibilityNodeInfo found = findSwitchNode(root);
                if (found != null) return found;
            }
        } catch (Exception e) {
            Log.e(TAG, "SWITCH_SEARCH: active root failed", e);
        }
        try {
            List<AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo window : windows) {
                    if (window == null) continue;
                    AccessibilityNodeInfo root = window.getRoot();
                    if (root == null) continue;
                    AccessibilityNodeInfo found = findSwitchNode(root);
                    if (found != null) return found;
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "SWITCH_SEARCH: getWindows failed", e);
        }
        Log.w(TAG, "SWITCH_SEARCH: switch not found");
        return null;
    }

    private AccessibilityNodeInfo findSwitchNode(AccessibilityNodeInfo node) {
        if (node == null) return null;
        CharSequence className = node.getClassName();
        CharSequence resourceId = node.getViewIdResourceName();
        if (className != null && "android.widget.Switch".equals(className.toString())) {
            Log.i(TAG, "SWITCH_MATCH: class=" + className + " resourceId=" + resourceId + " checked=" + node.isChecked() + " clickable=" + node.isClickable() + " enabled=" + node.isEnabled());
            return node;
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo found = findSwitchNode(node.getChild(i));
            if (found != null) return found;
        }
        return null;
    }

    public boolean clickSwitch() {
        AccessibilityNodeInfo node = findSwitchNodeInAllWindows();
        if (node == null) return false;
        return clickNode(node, "android.widget.Switch");
    }

    public boolean clickElement(String target) {
        if (target == null || target.trim().isEmpty()) {
            Log.w(TAG, "CLICK_ELEMENT: empty target");
            return false;
        }
        target = target.trim();
        AccessibilityNodeInfo node = findTargetNodeInAllWindows(target);
        if (node == null) {
            Log.w(TAG, "CLICK_ELEMENT: target not found: " + target);
            return false;
        }
        Log.i(TAG, "CLICK_ELEMENT: found target=" + target + " class=" + node.getClassName() + " clickable=" + node.isClickable() + " enabled=" + node.isEnabled() + " actions=" + node.getActionList());
        return clickNode(node, target);
    }

    private AccessibilityNodeInfo findTargetNodeInAllWindows(String target) {
        try {
            AccessibilityNodeInfo activeRoot = getRootInActiveWindow();
            if (activeRoot != null) {
                AccessibilityNodeInfo found = findMatchingNode(activeRoot, target);
                if (found != null) return found;
            }
        } catch (Exception e) {
            Log.e(TAG, "WINDOW_SEARCH: active root failed", e);
        }
        try {
            List<AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo window : windows) {
                    if (window == null) continue;
                    AccessibilityNodeInfo root = window.getRoot();
                    if (root == null) continue;
                    AccessibilityNodeInfo found = findMatchingNode(root, target);
                    if (found != null) return found;
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "WINDOW_SEARCH: getWindows failed", e);
        }
        Log.w(TAG, "WINDOW_SEARCH: target not found=" + target);
        return null;
    }

    private AccessibilityNodeInfo findMatchingNode(AccessibilityNodeInfo node, String target) {
        if (node == null) return null;
        String wanted = target.trim().toLowerCase();
        CharSequence text = node.getText();
        CharSequence description = node.getContentDescription();
        String textValue = text != null ? text.toString().trim() : "";
        String descValue = description != null ? description.toString().trim() : "";
        String textLower = textValue.toLowerCase();
        String descLower = descValue.toLowerCase();

        if (wanted.equals(textLower) || wanted.equals(descLower) ||
                (!textLower.isEmpty() && textLower.contains(wanted)) ||
                (!descLower.isEmpty() && descLower.contains(wanted))) {
            AccessibilityNodeInfo control = findRelatedClickableControl(node);
            return control != null ? control : node;
        }

        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo found = findMatchingNode(node.getChild(i), target);
            if (found != null) return found;
        }
        return null;
    }

    /*
     * IMPORTANT: Do not search the whole ancestor subtree here.
     * A Settings row is often inside a clickable RecyclerView. Searching
     * that subtree can select an unrelated clickable child/container and
     * make Nova scroll instead of opening the requested row.
     * Walk upward and use the nearest clickable ancestor only.
     */
    private AccessibilityNodeInfo findRelatedClickableControl(AccessibilityNodeInfo node) {
        if (node == null) return null;
        if (isPreferredClickableControl(node)) return node;

        AccessibilityNodeInfo current = node.getParent();
        int depth = 0;
        while (current != null && depth < 8) {
            Log.i(TAG, "SMART_CONTROL: ancestor depth=" + depth + " class=" + current.getClassName() + " clickable=" + current.isClickable());
            if (current.isEnabled() && current.isClickable()) {
                String className = current.getClassName() != null ? current.getClassName().toString() : "";
                if (!isScrollContainer(current)) {
                    Log.i(TAG, "SMART_CONTROL: using nearest clickable ancestor=" + className);
                    return current;
                }
                Log.i(TAG, "SMART_CONTROL: skipping scroll/container ancestor=" + className);
            }
            AccessibilityNodeInfo next = current.getParent();
            current.recycle();
            current = next;
            depth++;
        }
        return null;
    }

    private boolean isScrollContainer(AccessibilityNodeInfo node) {
        if (node == null) return false;
        if (node.isScrollable()) return true;
        CharSequence className = node.getClassName();
        if (className == null) return false;
        String value = className.toString();
        return value.contains("RecyclerView") || value.contains("ScrollView") || value.contains("ViewPager");
    }

    private boolean isPreferredClickableControl(AccessibilityNodeInfo node) {
        if (node == null || !node.isEnabled() || !node.isClickable()) return false;
        CharSequence className = node.getClassName();
        if (className == null) return false;
        String classValue = className.toString();
        return classValue.equals("android.widget.Switch") || classValue.equals("android.widget.ToggleButton") || classValue.equals("android.widget.CheckBox") || classValue.equals("android.widget.RadioButton") || node.isCheckable();
    }

    private boolean clickNode(AccessibilityNodeInfo node, String target) {
        if (node == null) return false;
        Log.i(TAG, "CLICK_NODE: target=" + target + " class=" + node.getClassName() + " text=" + node.getText() + " clickable=" + node.isClickable() + " enabled=" + node.isEnabled() + " actions=" + node.getActionList());

        if (node.isEnabled() && node.isClickable()) {
            boolean clicked = node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            Log.i(TAG, "CLICK_NODE: direct ACTION_CLICK=" + clicked);
            if (clicked) return true;
        }

        AccessibilityNodeInfo parent = node.getParent();
        int depth = 0;
        while (parent != null && depth < 8) {
            Log.i(TAG, "CLICK_NODE: parent depth=" + depth + " class=" + parent.getClassName() + " clickable=" + parent.isClickable() + " enabled=" + parent.isEnabled());
            if (parent.isEnabled() && parent.isClickable() && !isScrollContainer(parent)) {
                boolean clicked = parent.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                Log.i(TAG, "CLICK_NODE: parent ACTION_CLICK=" + clicked + " depth=" + depth);
                if (clicked) {
                    parent.recycle();
                    return true;
                }
            }
            AccessibilityNodeInfo next = parent.getParent();
            parent.recycle();
            parent = next;
            depth++;
        }

        android.graphics.Rect bounds = new android.graphics.Rect();
        node.getBoundsInScreen(bounds);
        if (bounds.isEmpty()) return false;
        float x = bounds.centerX();
        float y = bounds.centerY();
        android.graphics.Path path = new android.graphics.Path();
        path.moveTo(x, y);
        android.accessibilityservice.GestureDescription.StrokeDescription stroke = new android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, 100);
        android.accessibilityservice.GestureDescription gesture = new android.accessibilityservice.GestureDescription.Builder().addStroke(stroke).build();
        boolean dispatched = dispatchGesture(gesture, new android.accessibilityservice.AccessibilityService.GestureResultCallback() {
            @Override
            public void onCompleted(android.accessibilityservice.GestureDescription gestureDescription) {
                Log.i(TAG, "CLICK_NODE: gesture COMPLETED target=" + target);
            }
            @Override
            public void onCancelled(android.accessibilityservice.GestureDescription gestureDescription) {
                Log.w(TAG, "CLICK_NODE: gesture CANCELLED target=" + target);
            }
        }, null);
        Log.i(TAG, "CLICK_NODE: gesture dispatched=" + dispatched);
        return dispatched;
    }

    public boolean openBluetoothAndClick() {
        boolean opened = openBluetoothSettings();
        if (!opened) return false;
        return true;
    }

    public boolean openBluetoothSettings() {
        try {
            Intent intent = new Intent(Settings.ACTION_BLUETOOTH_SETTINGS);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
            return true;
        } catch (Exception e) {
            Log.e(TAG, "OPEN_BLUETOOTH: failed", e);
            return false;
        }
    }
}
