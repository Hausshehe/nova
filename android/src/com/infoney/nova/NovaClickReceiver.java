package com.infoney.nova;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class NovaClickReceiver extends BroadcastReceiver {

    private static final String TAG = "NovaAccessibility";

    @Override
    public void onReceive(Context context, Intent intent) {
        Log.i(TAG, "NovaClickReceiver.onReceive() CALLED");

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
            Log.i(TAG, "CLICK_ELEMENT result=" + result + " target=" + target);
            setResultCode(result ? 1 : 0);
            return;
        }

        if ("com.infoney.nova.SCROLL_WINDOW".equals(action)) {
            String direction = intent.getStringExtra("direction");
            boolean result = NovaAccessibilityService.instance != null
                    && NovaAccessibilityService.instance.scrollWindow(direction);
            Log.i(TAG, "SCROLL_WINDOW result=" + result + " direction=" + direction);
            setResultCode(result ? 1 : 0);
            return;
        }

        if ("com.infoney.nova.CLICK_TEXT".equals(action)) {
            String text = intent.getStringExtra("text");
            boolean result = NovaAccessibilityService.handleClickText(text);
            setResultCode(result ? 1 : 0);
        }
    }
}
