package dev.newal.code.lite;

import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

/**
 * A scheduled task's time (the engine is started, and kept awake while it looks at its tasks), a reboot (the alarm
 * set again) and the Allow / Deny buttons of an approval's notification (the answer sent to the engine).
 */
public class ScheduleReceiver extends BroadcastReceiver {
    static final String ALARM = "dev.newal.code.lite.SCHEDULE_ALARM";
    static final String APPROVE = "dev.newal.code.lite.SCHEDULE_APPROVE";

    @Override
    public void onReceive(Context ctx, Intent intent) {
        String action = intent == null ? "" : String.valueOf(intent.getAction());
        if (ALARM.equals(action)) {
            try {
                ScheduleAlarm.keepAwake(ctx, 600);
                ctx.startForegroundService(new Intent(ctx, AgentService.class));
            } catch (Exception e) {
                Log.w("NewAlCode", "scheduled task: cannot start the engine", e);
            }
        } else if (Intent.ACTION_BOOT_COMPLETED.equals(action) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            ScheduleAlarm.rearm(ctx);
        } else if (APPROVE.equals(action)) {
            PendingResult done = goAsync();
            String id = intent.getStringExtra("id");
            String answer = intent.getStringExtra("answer");
            int notification = intent.getIntExtra("notification", 0);
            new Thread(() -> {
                try {
                    answer(ctx, id, answer);
                    ctx.getSystemService(NotificationManager.class).cancel(notification);
                } catch (Exception e) {
                    Log.w("NewAlCode", "approval from the notification not sent", e);
                } finally {
                    done.finish();
                }
            }, "musab-approve").start();
        }
    }

    private static void answer(Context ctx, String id, String answer) throws Exception {
        URL url = new URL("http://127.0.0.1:" + Setup.PORT + "/api/approvals/" + URLEncoder.encode(id, "UTF-8"));
        HttpURLConnection c = (HttpURLConnection) url.openConnection(java.net.Proxy.NO_PROXY);
        c.setRequestMethod("POST");
        c.setConnectTimeout(5000);
        c.setReadTimeout(5000);
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/json");
        c.setRequestProperty("X-NewAl-Key", new Setup(ctx).key());
        try (OutputStream out = c.getOutputStream()) {
            out.write(("{\"answer\":\"" + ("deny".equals(answer) ? "deny" : "once") + "\"}")
                    .getBytes(StandardCharsets.UTF_8));
        }
        int code = c.getResponseCode();
        c.disconnect();
        if (code != 200) throw new java.io.IOException("the engine answered HTTP " + code);
    }
}
