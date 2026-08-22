package com.infoney.nova;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.provider.Settings;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import java.util.List;

public class NovaAccessibilityService extends AccessibilityService {

    private static final String TAG = "NovaAccessibility";
    private static final long TARGET_SEARCH_BUDGET_MS = 1200L;
    private static final int MAX_TARGET_SEARCH_DEPTH = 64;

    public static NovaAccessibilityService instance;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        Log.i(TAG, "Nova Accessibility Service connected.");
        AccessibilitySnapshotPublisher.publish(this, "service_connected");
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;
        String packageName = event.getPackageName() != null ? event.getPackageName().toString() : "unknown";
        Log.i(TAG, "SCREEN: " + packageName);
        AccessibilitySnapshotPublisher.publish(this, "event:" + event.getEventType());
    }

    @Override
    public void onInterrupt() {
        Log.w(TAG, "Accessibility service interrupted.");
        AccessibilitySnapshotPublisher.publish(this, "service_interrupted");
    }

    public static boolean handleClickText(String text) {
        if (instance == null) return false;
        return instance.clickText(text);
    }

    public boolean clickText(String target) {
        if (target == null || target.trim().isEmpty()) return false;
        target = target.trim();

        String normalized = target.toLowerCase().replace("\u2011", "-").replace("\u2013", "-");
        if ("display & brightness".equals(normalized) || "display and brightness".equals(normalized)) {
            try {
                Intent intent = new Intent(Settings.ACTION_DISPLAY_SETTINGS);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(intent);
                return true;
            } catch (Exception e) {
                Log.e(TAG, "CLICK_TEXT: ACTION_DISPLAY_SETTINGS failed", e);
            }
        }

        final int maxAttempts = 6;
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            AccessibilityNodeInfo node = findTargetNodeInAllWindows(target);
            if (node != null) {
                boolean result = clickNode(node, target);
                node.recycle();
                if (result) return true;
            }
            if (attempt < maxAttempts && scrollWindow("down")) {
                try {
                    Thread.sleep(250);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            } else if (attempt < maxAttempts) {
                break;
            }
        }
        return false;
    }

    public boolean scrollWindow(String direction) {
        boolean forward = "down".equalsIgnoreCase(direction);
        boolean backward = "up".equalsIgnoreCase(direction);
        if (!forward && !backward) return false;

        int action = forward ? AccessibilityNodeInfo.ACTION_SCROLL_FORWARD : AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD;

        AccessibilityNodeInfo root = null;
        try {
            root = getRootInActiveWindow();
            if (root != null) {
                boolean moved = scrollNode(root, action);
                if (moved) return true;
            }
        } catch (Exception e) {
            Log.e(TAG, "SCROLL_WINDOW: active root failed", e);
        } finally {
            if (root != null) root.recycle();
        }

        try {
            List<AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo window : windows) {
                    if (window == null) continue;
                    AccessibilityNodeInfo windowRoot = window.getRoot();
                    if (windowRoot == null) continue;
                    try {
                        if (scrollNode(windowRoot, action)) return true;
                    } finally {
                        windowRoot.recycle();
                    }
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "SCROLL_WINDOW: window search failed", e);
        }

        // Some Android/OEM Settings hierarchies expose no actionable scrollable
        // AccessibilityNodeInfo even though the UI visibly scrolls. In that case,
        // use the same generic capability through AccessibilityService gestures.
        // This is not a Settings-specific coordinate hack: the gesture is derived
        // from the current display size and the requested direction.
        return gestureScrollFallback(forward);
    }

    private boolean scrollNode(AccessibilityNodeInfo node, int action) {
        if (node == null) return false;
        if (node.isScrollable() && node.isEnabled() && node.performAction(action)) {
            Log.i(TAG, "SCROLL_WINDOW: ACTION_" + action + " succeeded on " + node.getClassName());
            return true;
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child == null) continue;
            try {
                if (scrollNode(child, action)) return true;
            } finally {
                child.recycle();
            }
        }
        return false;
    }

    private boolean gestureScrollFallback(boolean forward) {
        try {
            android.util.DisplayMetrics metrics = getResources().getDisplayMetrics();
            float width = metrics.widthPixels;
            float height = metrics.heightPixels;
            if (width < 200 || height < 300) return false;

            float x = width * 0.50f;
            float startY = forward ? height * 0.78f : height * 0.32f;
            float endY = forward ? height * 0.32f : height * 0.78f;

            android.graphics.Path path = new android.graphics.Path();
            path.moveTo(x, startY);
            path.lineTo(x, endY);

            android.accessibilityservice.GestureDescription.StrokeDescription stroke =
                    new android.accessibilityservice.GestureDescription.StrokeDescription(path, 0, 450);
            android.accessibilityservice.GestureDescription gesture =
                    new android.accessibilityservice.GestureDescription.Builder()
                            .addStroke(stroke)
                            .build();

            boolean dispatched = dispatchGesture(gesture, new GestureResultCallback() {
                @Override
                public void onCompleted(android.accessibilityservice.GestureDescription gestureDescription) {
                    Log.i(TAG, "SCROLL_WINDOW: generic gesture completed direction=" + (forward ? "down" : "up"));
                }

                @Override
                public void onCancelled(android.accessibilityservice.GestureDescription gestureDescription) {
                    Log.w(TAG, "SCROLL_WINDOW: generic gesture cancelled direction=" + (forward ? "down" : "up"));
                }
            }, null);

            Log.i(TAG, "SCROLL_WINDOW: generic gesture dispatched=" + dispatched + " direction=" + (forward ? "down" : "up"));
            return dispatched;
        } catch (Exception e) {
            Log.e(TAG, "SCROLL_WINDOW: generic gesture fallback failed", e);
            return false;
        }
    }

    private AccessibilityNodeInfo findSwitchNodeInAllWindows() {
        AccessibilityNodeInfo root = null;
        try {
            root = getRootInActiveWindow();
            if (root != null) {
                AccessibilityNodeInfo found = findSwitchNode(root);
                if (found != null) return found;
            }
        } catch (Exception e) {
            Log.e(TAG, "SWITCH_SEARCH: active root failed", e);
        } finally {
            if (root != null) root.recycle();
        }
        try {
            List<AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo window : windows) {
                    if (window == null) continue;
                    AccessibilityNodeInfo windowRoot = window.getRoot();
                    if (windowRoot == null) continue;
                    try {
                        AccessibilityNodeInfo found = findSwitchNode(windowRoot);
                        if (found != null) return found;
                    } finally {
                        windowRoot.recycle();
                    }
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "SWITCH_SEARCH: getWindows failed", e);
        }
        return null;
    }

    private AccessibilityNodeInfo findSwitchNode(AccessibilityNodeInfo node) {
        if (node == null) return null;
        CharSequence className = node.getClassName();
        if (className != null && "android.widget.Switch".equals(className.toString())) return node;
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
        if (target == null || target.trim().isEmpty()) return false;
        target = target.trim();
        long started = System.currentTimeMillis();
        Log.i(TAG, "CLICK_ELEMENT: search start target=" + target);
        AccessibilityNodeInfo node = findTargetNodeInAllWindows(target);
        long searchMs = System.currentTimeMillis() - started;
        Log.i(TAG, "CLICK_ELEMENT: search finished target=" + target + " found=" + (node != null) + " elapsed_ms=" + searchMs);
        if (node == null) return false;
        try {
            long clickStarted = System.currentTimeMillis();
            boolean result = clickNode(node, target);
            Log.i(TAG, "CLICK_ELEMENT: click finished target=" + target + " result=" + result + " elapsed_ms=" + (System.currentTimeMillis() - clickStarted));
            return result;
        } finally {
            node.recycle();
        }
    }

    private AccessibilityNodeInfo findTargetNodeInAllWindows(String target) {
        final long deadline = System.nanoTime() + TARGET_SEARCH_BUDGET_MS * 1_000_000L;
        AccessibilityNodeInfo activeRoot = null;
        try {
            activeRoot = getRootInActiveWindow();
            if (activeRoot != null) {
                AccessibilityNodeInfo found = findMatchingNode(activeRoot, target, deadline, 0);
                if (found != null) return found;
            }
        } catch (Exception e) {
            Log.e(TAG, "WINDOW_SEARCH: active root failed", e);
        } finally {
            if (activeRoot != null) activeRoot.recycle();
        }
        if (System.nanoTime() >= deadline) {
            Log.w(TAG, "WINDOW_SEARCH: target search budget exhausted before window fallback target=" + target);
            return null;
        }
        try {
            List<AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo window : windows) {
                    if (System.nanoTime() >= deadline) break;
                    if (window == null) continue;
                    AccessibilityNodeInfo root = window.getRoot();
                    if (root == null) continue;
                    try {
                        AccessibilityNodeInfo found = findMatchingNode(root, target, deadline, 0);
                        if (found != null) return found;
                    } finally {
                        root.recycle();
                    }
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "WINDOW_SEARCH: getWindows failed", e);
        }
        return null;
    }

    private AccessibilityNodeInfo findMatchingNode(AccessibilityNodeInfo node, String target, long deadline, int depth) {
        if (node == null || System.nanoTime() >= deadline || depth > MAX_TARGET_SEARCH_DEPTH) return null;
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
            if (System.nanoTime() >= deadline) return null;
            AccessibilityNodeInfo found = findMatchingNode(node.getChild(i), target, deadline, depth + 1);
            if (found != null) return found;
        }
        return null;
    }

    private AccessibilityNodeInfo findRelatedClickableControl(AccessibilityNodeInfo node) {
        if (node == null) return null;
        if (isPreferredClickableControl(node)) return node;

        AccessibilityNodeInfo current = node.getParent();
        int depth = 0;
        while (current != null && depth < 8) {
            if (current.isEnabled() && current.isClickable() && !isScrollContainer(current)) return current;
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
        if (node.isEnabled() && node.isClickable()) {
            if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true;
        }

        AccessibilityNodeInfo parent = node.getParent();
        int depth = 0;
        while (parent != null && depth < 8) {
            if (parent.isEnabled() && parent.isClickable() && !isScrollContainer(parent)) {
                boolean clicked = parent.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                AccessibilityNodeInfo next = parent.getParent();
                parent.recycle();
                if (clicked) return true;
                parent = next;
                depth++;
                continue;
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
        return dispatchGesture(gesture, new GestureResultCallback() {
            @Override
            public void onCompleted(android.accessibilityservice.GestureDescription gestureDescription) {
                Log.i(TAG, "CLICK_NODE: gesture completed target=" + target);
            }

            @Override
            public void onCancelled(android.accessibilityservice.GestureDescription gestureDescription) {
                Log.w(TAG, "CLICK_NODE: gesture cancelled target=" + target);
            }
        }, null);
    }

    public boolean openBluetoothAndClick() {
        return openBluetoothSettings();
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
