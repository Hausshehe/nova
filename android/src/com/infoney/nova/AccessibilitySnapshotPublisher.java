package com.infoney.nova;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/** Publishes the latest live accessibility hierarchy for Nova's Python observer. */
public final class AccessibilitySnapshotPublisher {

    private static final String SNAPSHOT_FILE = "nova_accessibility_snapshot.json";
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();
    private static final AtomicLong GENERATION = new AtomicLong(0);
    private static final AtomicBoolean RUNNING = new AtomicBoolean(false);

    private AccessibilitySnapshotPublisher() {}

    public static void publish(AccessibilityService service, String reason) {
        if (service == null) return;
        GENERATION.incrementAndGet();
        if (!RUNNING.compareAndSet(false, true)) return;

        EXECUTOR.execute(() -> {
            try {
                long seen;
                do {
                    seen = GENERATION.get();
                    write(service, reason);
                } while (seen != GENERATION.get());
            } catch (Exception ignored) {
                // The Python observer can fall back to UIAutomator when the
                // accessibility snapshot cannot be published.
            } finally {
                RUNNING.set(false);
                // Only schedule another write if a new event arrived after the
                // worker's last snapshot. Do not use GENERATION > 0 here:
                // generation is intentionally monotonic and therefore remains
                // positive for the lifetime of the service.
                if (GENERATION.get() != 0 && RUNNING.compareAndSet(false, true)) {
                    long latest = GENERATION.get();
                    if (latest != 0) {
                        EXECUTOR.execute(() -> {
                            try {
                                write(service, "coalesced_event");
                            } catch (Exception ignored) {
                                // Fallback observer remains authoritative.
                            } finally {
                                RUNNING.set(false);
                            }
                        });
                    } else {
                        RUNNING.set(false);
                    }
                }
            }
        });
    }

    private static void write(AccessibilityService service, String reason) throws Exception {
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        if (root == null) return;

        JSONArray nodes = new JSONArray();
        JSONArray scrollable = new JSONArray();
        String foregroundPackage = root.getPackageName() == null
                ? ""
                : root.getPackageName().toString();

        collect(root, null, nodes, scrollable);
        root.recycle();

        JSONObject snapshot = new JSONObject();
        snapshot.put("success", true);
        snapshot.put("verified", true);
        snapshot.put("source", "accessibility_service");
        snapshot.put("timestamp_ms", System.currentTimeMillis());
        snapshot.put("reason", reason == null ? "event" : reason);
        snapshot.put("foreground_package", foregroundPackage);
        snapshot.put("nodes", nodes);
        snapshot.put("scrollable", scrollable);

        File directory = service.getFilesDir();
        File target = new File(directory, SNAPSHOT_FILE);
        File temp = new File(directory, SNAPSHOT_FILE + ".tmp");
        try (FileOutputStream out = new FileOutputStream(temp, false)) {
            out.write(snapshot.toString().getBytes(StandardCharsets.UTF_8));
            out.flush();
        }

        if (target.exists()) target.delete();
        temp.renameTo(target);
    }

    private static void collect(
            AccessibilityNodeInfo node,
            AccessibilityNodeInfo actionableAncestor,
            JSONArray nodes,
            JSONArray scrollable
    ) throws Exception {
        JSONObject item = nodeObject(node, actionableAncestor);
        if (item != null) nodes.put(item);

        if (node.isScrollable() && node.isEnabled()) {
            String bounds = bounds(node);
            if (!bounds.isEmpty()) scrollable.put(bounds);
        }

        AccessibilityNodeInfo nextAncestor = actionableAncestor;
        if (node.isEnabled() && node.isClickable()) nextAncestor = node;

        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child == null) continue;
            collect(child, nextAncestor, nodes, scrollable);
            child.recycle();
        }
    }

    private static JSONObject nodeObject(
            AccessibilityNodeInfo node,
            AccessibilityNodeInfo actionableAncestor
    ) throws Exception {
        String text = value(node.getText());
        String description = value(node.getContentDescription());
        String resourceId = node.getViewIdResourceName() == null ? "" : node.getViewIdResourceName();
        String className = node.getClassName() == null ? "" : node.getClassName().toString();
        String packageName = node.getPackageName() == null ? "" : node.getPackageName().toString();

        if (text.isEmpty() && description.isEmpty() && resourceId.isEmpty() && className.isEmpty()) {
            return null;
        }

        JSONObject item = new JSONObject();
        item.put("text", text);
        item.put("content_description", description);
        item.put("resource_id", resourceId);
        item.put("class", className);
        item.put("package", packageName);
        item.put("bounds", bounds(node));
        item.put("clickable", node.isClickable());
        item.put("enabled", node.isEnabled());
        item.put("focusable", node.isFocusable());
        item.put("scrollable", node.isScrollable());
        item.put("selected", node.isSelected());
        item.put("checked", node.isChecked());

        if (!node.isClickable() && actionableAncestor != null) {
            item.put("actionable_ancestor", ancestorObject(actionableAncestor));
        }

        return item;
    }

    private static JSONObject ancestorObject(AccessibilityNodeInfo node) throws Exception {
        JSONObject ancestor = new JSONObject();
        ancestor.put("text", value(node.getText()));
        ancestor.put("content_description", value(node.getContentDescription()));
        ancestor.put("resource_id", node.getViewIdResourceName() == null ? "" : node.getViewIdResourceName());
        ancestor.put("class", node.getClassName() == null ? "" : node.getClassName().toString());
        ancestor.put("package", node.getPackageName() == null ? "" : node.getPackageName().toString());
        ancestor.put("bounds", bounds(node));
        ancestor.put("clickable", node.isClickable());
        ancestor.put("enabled", node.isEnabled());
        return ancestor;
    }

    private static String value(CharSequence value) {
        return value == null ? "" : value.toString().trim();
    }

    private static String bounds(AccessibilityNodeInfo node) {
        android.graphics.Rect rect = new android.graphics.Rect();
        node.getBoundsInScreen(rect);
        if (rect.isEmpty()) return "";
        return "[" + rect.left + "," + rect.top + "][" + rect.right + "," + rect.bottom + "]";
    }
}
