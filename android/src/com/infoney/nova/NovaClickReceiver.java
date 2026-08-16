package com.infoney.nova;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class NovaClickReceiver extends BroadcastReceiver {

    private static final String TAG = "NovaAccessibility";

    @Override
    public void onReceive(Context context, Intent intent) {

        Log.i(TAG, "🔥 NovaClickReceiver.onReceive() CALLED");

        if (intent == null) {
            Log.w(TAG, "CLICK_TEXT: intent is null");
            return;
        }

        String action = intent.getAction();

        Log.i(TAG, "NovaClickReceiver action=" + action);

        if ("com.infoney.nova.OPEN_BLUETOOTH".equals(action)) {

            Log.i(TAG, "Received OPEN_BLUETOOTH");

            if (NovaAccessibilityService.instance != null) {

                Log.i(
                        TAG,
                        "OPEN_BLUETOOTH: accessibility service instance EXISTS"
                );

                boolean result =
                        NovaAccessibilityService.instance
                                .openBluetoothAndClick();

                Log.i(
                        TAG,
                        "OPEN_BLUETOOTH result=" + result
                );

            } else {

                Log.w(
                        TAG,
                        "OPEN_BLUETOOTH: accessibility service unavailable"
                );
            }

            return;
        }

        if ("com.infoney.nova.CLICK_SWITCH".equals(action)) {

            Log.i(TAG, "Received CLICK_SWITCH");

            if (NovaAccessibilityService.instance == null) {

                Log.w(
                        TAG,
                        "CLICK_SWITCH: accessibility service instance is NULL"
                );

                return;
            }

            Log.i(
                    TAG,
                    "CLICK_SWITCH: accessibility service instance EXISTS"
            );

            boolean result =
                    NovaAccessibilityService.instance.clickSwitch();

            Log.i(
                    TAG,
                    "CLICK_SWITCH result=" + result
            );

            return;
        }

        if ("com.infoney.nova.CLICK_ELEMENT".equals(action)) {

            String target =
                    intent.getStringExtra("target");

            Log.i(
                    TAG,
                    "Received CLICK_ELEMENT: " + target
            );

            if (NovaAccessibilityService.instance == null) {

                Log.w(
                        TAG,
                        "CLICK_ELEMENT: accessibility service instance is NULL"
                );

                return;
            }

            Log.i(
                    TAG,
                    "CLICK_ELEMENT: accessibility service instance EXISTS"
            );

            boolean result =
                    NovaAccessibilityService.instance
                            .clickElement(target);

            Log.i(
                    TAG,
                    "CLICK_ELEMENT result=" + result
            );

            return;
        }

        if ("com.infoney.nova.CLICK_TEXT".equals(action)) {

            String text =
                    intent.getStringExtra("text");

            Log.i(
                    TAG,
                    "Received CLICK_TEXT: " + text
            );

            if (NovaAccessibilityService.instance == null) {

                Log.w(
                        TAG,
                        "CLICK_TEXT: accessibility service instance is NULL"
                );

                return;
            }

            Log.i(
                    TAG,
                    "CLICK_TEXT: accessibility service instance EXISTS"
            );

            boolean result =
                    NovaAccessibilityService.handleClickText(text);

            Log.i(
                    TAG,
                    "CLICK_TEXT: handleClickText returned="
                            + result
            );
        }
    }
}
