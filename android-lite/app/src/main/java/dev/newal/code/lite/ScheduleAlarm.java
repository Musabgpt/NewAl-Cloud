package dev.newal.code.lite;

import android.app.AlarmManager;
import android.app.KeyguardManager;
import android.app.Notification;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.PowerManager;

import org.json.JSONObject;

/**
 * What scheduled tasks (schedule.py) need from Android: an alarm that wakes the engine at the next task's time (kept
 * across reboots), the CPU kept awake while a run works, the screen turned on before a task that uses it (and off
 * after), and Allow / Deny on an approval's notification. A secure lock (PIN, pattern, fingerprint) is never opened:
 * Android lets only the user do that, so the task waits for the unlock.
 */
final class ScheduleAlarm {
    private static final String PREFS = "musab_schedule";
    private static PowerManager.WakeLock awake;

    private ScheduleAlarm() {
    }

    private static PendingIntent alarmIntent(Context ctx) {
        Intent i = new Intent(ctx, ScheduleReceiver.class).setAction(ScheduleReceiver.ALARM);
        return PendingIntent.getBroadcast(ctx, 41, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    /** The engine is woken at `at` (ms since 1970; 0: no alarm). */
    static JSONObject arm(Context ctx, long at) throws Exception {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putLong("next", at).apply();
        AlarmManager am = ctx.getSystemService(AlarmManager.class);
        PendingIntent pi = alarmIntent(ctx);
        if (at <= 0) {
            am.cancel(pi);
            return Phone.ok("no alarm");
        }
        boolean exact = Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms();
        if (exact) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
        } else {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);   // within minutes of its time
        }
        return Phone.ok(exact ? "alarm set" : "alarm set (approximate: exact alarms are not allowed)");
    }

    /** After a reboot (alarms do not survive one): the saved time again, or in a minute when it has passed. */
    static void rearm(Context ctx) {
        SharedPreferences p = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        long at = p.getLong("next", 0);
        if (at <= 0) return;
        try {
            arm(ctx, Math.max(at, System.currentTimeMillis() + 60_000));
        } catch (Exception ignored) {
        }
    }

    /** The CPU stays awake for `seconds` (0: no longer), while a scheduled run works with the screen off. */
    static synchronized JSONObject keepAwake(Context ctx, int seconds) throws Exception {
        if (awake != null && awake.isHeld()) awake.release();
        if (seconds > 0) {
            if (awake == null) {
                awake = ctx.getSystemService(PowerManager.class)
                        .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MusabAI:schedule");
                awake.setReferenceCounted(false);
            }
            awake.acquire(Math.min(seconds, 3600) * 1000L);
        }
        return Phone.ok(seconds > 0 ? "awake for " + seconds + " s" : "released");
    }

    /**
     * Before a task that uses the screen: {"locked": true} when a secure lock is on (only the user opens it), else
     * the screen on and a swipe lock dismissed ({"woke": true} when it was off).
     */
    @SuppressWarnings("deprecation")
    static JSONObject wake(Context ctx) throws Exception {
        KeyguardManager km = ctx.getSystemService(KeyguardManager.class);
        PowerManager pm = ctx.getSystemService(PowerManager.class);
        JSONObject r = Phone.ok("the screen is on and unlocked");
        if (pm.isInteractive() && !km.isKeyguardLocked()) return r;
        if (km.isKeyguardLocked() && km.isDeviceSecure()) {
            r.put("locked", true);
            r.put("text", "the phone is locked with a PIN, pattern or fingerprint: only the user unlocks it");
            return r;
        }
        PowerManager.WakeLock screen = pm.newWakeLock(PowerManager.SCREEN_BRIGHT_WAKE_LOCK
                | PowerManager.ACQUIRE_CAUSES_WAKEUP, "MusabAI:wake");
        screen.acquire(10_000);
        try {
            ctx.startActivity(new Intent(ctx, WakeActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                    | Intent.FLAG_ACTIVITY_NO_ANIMATION | Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS));
        } catch (RuntimeException ignored) {
            // Android may refuse an activity from the background; the screen is on all the same
        }
        for (int i = 0; i < 40 && !(pm.isInteractive() && !km.isKeyguardLocked()); i++) Thread.sleep(100);
        boolean open = pm.isInteractive() && !km.isKeyguardLocked();
        r.put("woke", open);
        r.put("locked", !open && km.isKeyguardLocked());
        r.put("text", open ? "the screen was turned on" : "the screen could not be opened");
        return r;
    }

    /** After a run that turned the screen on: off again (Android 9 and up, with the accessibility service on). */
    static JSONObject sleepScreen() throws Exception {
        PhoneControlService s = PhoneControlService.on;
        if (s != null && Build.VERSION.SDK_INT >= 28) {
            s.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_LOCK_SCREEN);
            return Phone.ok("the screen is off");
        }
        return Phone.ok("the screen turns off by itself");
    }

    /** Allow and Deny on the notification of a tool call waiting for approval. */
    static void approvalActions(Context ctx, Notification.Builder nb, String approval, int notificationId) {
        String[][] answers = {{"once", ctx.getString(R.string.approve_allow)}, {"deny", ctx.getString(R.string.approve_deny)}};
        for (int i = 0; i < answers.length; i++) {
            Intent a = new Intent(ctx, ScheduleReceiver.class).setAction(ScheduleReceiver.APPROVE)
                    .putExtra("id", approval).putExtra("answer", answers[i][0]).putExtra("notification", notificationId);
            PendingIntent pi = PendingIntent.getBroadcast(ctx, notificationId * 2 + i, a,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            nb.addAction(new Notification.Action.Builder(null, answers[i][1], pi).build());
        }
    }
}
