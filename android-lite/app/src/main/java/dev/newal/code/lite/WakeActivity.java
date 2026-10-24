package dev.newal.code.lite;

import android.app.Activity;
import android.app.KeyguardManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.WindowManager;

/**
 * Turns the screen on and dismisses a swipe lock for a scheduled task that uses the screen, then closes. A secure
 * lock is never dismissed here (ScheduleAlarm.wake does not start this activity then).
 */
public class WakeActivity extends Activity {
    @Override
    @SuppressWarnings("deprecation")
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        } else {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                    | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        }
        KeyguardManager km = getSystemService(KeyguardManager.class);
        if (km != null && km.isKeyguardLocked() && !km.isDeviceSecure()) {
            km.requestDismissKeyguard(this, new KeyguardManager.KeyguardDismissCallback() {
                @Override public void onDismissSucceeded() { finish(); }
                @Override public void onDismissError() { finish(); }
                @Override public void onDismissCancelled() { finish(); }
            });
        }
        new Handler(Looper.getMainLooper()).postDelayed(this::finish, 3000);
    }
}
