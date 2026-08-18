package com.infoney.nova;

import android.accessibilityservice.AccessibilityService;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;
import android.view.accessibility.AccessibilityNodeInfo;

public class NovaClickReceiver extends BroadcastReceiver {

    private static final String TAG = "NovaAccessibility";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) {
            setResultCode(0);
            return;
        }

        String action = intent.getAction();
        Log.i(TAG, "NovaClickReceiver action=" + action);

        if ("com.infoney.nova.OPEN_BLUETOOTH".equals(action)) {
            boolean result = NovaAccessibilityService.instance != null
                    && NovaAccessibilityService.instance.openBluetoothAndClick();
            setResultCode(result ? 1 : 0);
            return;
        }

        if ("com.infoney.nova.CLICK_SWITCH".equals(action)) {
            boolean result = NovaAccessibilityService.instance != null
                    && NovaAccessibilityService.instance.clickSwitch();
            setResultCode(result ? 1 : 0);
            return;
        }

        if ("com.infoney.nova.CLICK_ELEMENT".equals(action)) {
            String target = intent.getStringExtra("target");
            boolean result = NovaAccessibilityService.instance != null
                    && NovaAccessibilityService.instance.clickElement(target);
            Log.i(TAG, "CLICK_ELEMENT target=" + target + " result=" + result);
            setResultCode(result ? 1 : 0);
            return;
        }

        if ("com.infoney.nova.SCROLL_WINDOW".equals(action)) {
            String direction = intent.getStringExtra("direction");
            boolean result = scrollWindow(direction);
            Log.i(TAG, "SCROLL_WINDOW direction=" + direction + " result=" + result);
            setResultCode(result ? 1 : 0);
            return;
        }

        if ("com.infoney.nova.CLICK_TEXT".equals(action)) {
            String text = intent.getStringExtra("text");
            boolean result = NovaAccessibilityService.handleClickText(text);
            setResultCode(result ? 1 : 0);
        }
    }

    private boolean scrollWindow(String direction) {
        if (NovaAccessibilityService.instance == null) return false;
        boolean forward = "down".equalsIgnoreCase(direction);
        boolean backward = "up".equalsIgnoreCase(direction);
        if (!forward && !backward) return false;

        AccessibilityNodeInfo root = NovaAccessibilityService.instance.getRootInActiveWindow();
        if (root == null) return false;
        try {
            int action = forward
                    ? AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                    : AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD;
            return scrollNode(root, action);
        } finally {
            root.recycle();
        }
    }

    private boolean scrollNode(AccessibilityNodeInfo node, int action) {
        if (node == null) return false;
        if (node.isEnabled() && node.isScrollable()
                && node.performAction(action)) {
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
}
