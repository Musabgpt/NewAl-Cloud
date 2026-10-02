package com.musab.newalcloud;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Single-screen experiment: chat with a free cloud LLM API instead of a local GGUF model. */
public class MainActivity extends Activity {
    private static final String SYSTEM_PROMPT =
            "You are an expert coding assistant. Reply with complete, runnable code and a minimal explanation. "
                    + "Answer in the language the user writes in.";
    private static final int MAX_TOKENS = 4096;
    private static final double TEMPERATURE = 0.2;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final List<RemoteChat.Msg> history = new ArrayList<>();
    private final StringBuilder transcript = new StringBuilder();
    private final StringBuilder live = new StringBuilder();
    private final Object renderLock = new Object();
    private boolean renderScheduled;

    private SharedPreferences prefs;
    private Spinner providerSpinner;
    private EditText endpointField, modelField, keyField, input;
    private LinearLayout settingsBox;
    private TextView chat, status, keyHint;
    private ScrollView scroll;
    private Button send;
    private int current = -1;
    private volatile RemoteChat client;
    private boolean busy;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("newal_cloud", MODE_PRIVATE);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFF0D1117);
        root.setOnApplyWindowInsetsListener((v, in) -> {
            int top, bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets i = in.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                top = i.top; bottom = i.bottom;
            } else {
                top = in.getSystemWindowInsetTop(); bottom = in.getSystemWindowInsetBottom();
            }
            v.setPadding(dp(10), top + dp(8), dp(10), bottom + dp(8));
            return in;
        });

        // Top bar
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        TextView title = new TextView(this);
        title.setText("NewAl Cloud");
        title.setTextSize(18);
        title.setTextColor(0xFFE6EDF3);
        bar.addView(title, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        Button gear = new Button(this);
        gear.setText("⚙");
        gear.setOnClickListener(v -> settingsBox.setVisibility(
                settingsBox.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE));
        bar.addView(gear);
        Button clear = new Button(this);
        clear.setText("🗑");
        clear.setOnClickListener(v -> clearChat());
        bar.addView(clear);
        root.addView(bar);

        // Settings
        settingsBox = new LinearLayout(this);
        settingsBox.setOrientation(LinearLayout.VERTICAL);
        providerSpinner = new Spinner(this);
        providerSpinner.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, Providers.names()));
        settingsBox.addView(providerSpinner);
        endpointField = field("Endpoint (…/chat/completions)", false);
        modelField = field("Model", false);
        keyField = field("API key", true);
        settingsBox.addView(endpointField);
        settingsBox.addView(modelField);
        settingsBox.addView(keyField);
        keyHint = new TextView(this);
        keyHint.setTextSize(12);
        keyHint.setTextColor(0xFF8B949E);
        settingsBox.addView(keyHint);
        root.addView(settingsBox);

        // Chat area
        scroll = new ScrollView(this);
        chat = new TextView(this);
        chat.setTextSize(15);
        chat.setTextColor(0xFFE6EDF3);
        chat.setTextIsSelectable(true);
        chat.setTextDirection(View.TEXT_DIRECTION_FIRST_STRONG);
        chat.setPadding(dp(4), dp(8), dp(4), dp(8));
        scroll.addView(chat);
        root.addView(scroll, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));

        status = new TextView(this);
        status.setTextSize(12);
        status.setTextColor(0xFF8B949E);
        root.addView(status);

        // Input row
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        input = new EditText(this);
        input.setHint("اكتب طلبك…");
        input.setHintTextColor(0xFF8B949E);
        input.setTextColor(0xFFE6EDF3);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        input.setMaxLines(5);
        row.addView(input, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        send = new Button(this);
        send.setText("➤");
        send.setOnClickListener(v -> onSend());
        row.addView(send);
        root.addView(row);

        setContentView(root);
        root.requestApplyInsets();

        providerSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> p, View v, int pos, long id) {
                if (current >= 0 && current != pos) saveFields();
                current = pos;
                loadFields();
                prefs.edit().putInt("provider", pos).apply();
            }
            @Override public void onNothingSelected(AdapterView<?> p) {}
        });
        providerSpinner.setSelection(Math.max(0, Math.min(Providers.ALL.length - 1, prefs.getInt("provider", 0))));
        // Zero-setup mode: all routing fields are preconfigured and the settings panel stays hidden.
        settingsBox.setVisibility(View.GONE);
        status.setText("جاهز • FreeLLMAPI Auto Free — لا يحتاج API key");
    }

    private EditText field(String hint, boolean secret) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setHintTextColor(0xFF8B949E);
        e.setTextColor(0xFFE6EDF3);
        e.setSingleLine(true);
        e.setTextDirection(View.TEXT_DIRECTION_LTR);
        e.setInputType(InputType.TYPE_CLASS_TEXT
                | (secret ? InputType.TYPE_TEXT_VARIATION_PASSWORD : InputType.TYPE_TEXT_VARIATION_URI));
        return e;
    }

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    // ------------------------------------------------------------------ settings persistence

    private void loadFields() {
        Providers.P p = Providers.ALL[current];
        endpointField.setText(prefs.getString("endpoint_" + current, p.endpoint));
        modelField.setText(prefs.getString("model_" + current, p.model));
        keyField.setText(prefs.getString("key_" + current, ""));
        keyHint.setText(p.keyUrl.isEmpty() ? "المفتاح يُحفظ على هذا الجهاز فقط"
                : "احصل على مفتاح مجاني من: " + p.keyUrl + " (يُحفظ على هذا الجهاز فقط)");
    }

    private void saveFields() {
        if (current < 0) return;
        prefs.edit()
                .putString("endpoint_" + current, endpointField.getText().toString().trim())
                .putString("model_" + current, modelField.getText().toString().trim())
                .putString("key_" + current, keyField.getText().toString().trim())
                .apply();
    }

    @Override protected void onPause() {
        saveFields();
        super.onPause();
    }

    @Override protected void onDestroy() {
        RemoteChat c = client;
        if (c != null) c.cancel();
        executor.shutdownNow();
        super.onDestroy();
    }

    // ------------------------------------------------------------------ chat

    private void onSend() {
        if (busy) {
            RemoteChat c = client;
            if (c != null) c.cancel();
            return;
        }
        String q = input.getText().toString().trim();
        if (q.isEmpty()) return;
        saveFields();
        // FreeLLMAPI/Kilo keyless route: no provider setup or API key is required.
        final String endpoint = Providers.ENDPOINT;
        final String model = Providers.MODEL;
        final String key = "";
        input.setText("");
        history.add(new RemoteChat.Msg("user", q));
        transcript.append("🧑 ").append(q).append("\n\n🤖 ");
        synchronized (live) { live.setLength(0); }
        setBusy(true);
        status.setText("جاري التوجيه تلقائياً إلى نموذج مجاني…");
        render();

        final List<RemoteChat.Msg> turns = new ArrayList<>();
        turns.add(new RemoteChat.Msg("system", SYSTEM_PROMPT));
        turns.addAll(history);
        final RemoteChat c = new RemoteChat();
        client = c;
        executor.execute(() -> {
            try {
                RemoteChat.Result r = c.chat(endpoint, key, model, turns, MAX_TOKENS, TEMPERATURE, delta -> {
                    synchronized (live) { live.append(delta); }
                    scheduleRender();
                });
                String metrics = String.format(Locale.US, "%s • أول token %dms • إجمالي %dms",
                        model, r.firstTokenMs, r.totalMs);
                ui.post(() -> finishTurn(r.text, null, metrics));
            } catch (RemoteChat.ApiException e) {
                ui.post(() -> finishTurn("", describe(e), "فشل الطلب"));
            } catch (IOException e) {
                String m = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
                ui.post(() -> finishTurn("", m, "فشل الاتصال"));
            }
        });
    }

    private static String describe(RemoteChat.ApiException e) {
        StringBuilder b = new StringBuilder("HTTP ").append(e.code);
        if (e.code == 429) {
            b.append(" — تجاوزت حد الاستخدام");
            if (e.retryAfter != null) b.append("، أعد المحاولة بعد ").append(e.retryAfter).append(" ثانية");
        } else if (e.code == 401 || e.code == 403) {
            b.append(" — تحقق من المفتاح");
        } else if (e.code == 404) {
            b.append(" — تحقق من الرابط واسم النموذج");
        }
        String body = e.body == null ? "" : e.body.trim();
        if (!body.isEmpty()) b.append('\n').append(body.length() > 300 ? body.substring(0, 300) + "…" : body);
        return b.toString();
    }

    /** Runs on the UI thread when a turn ends (normally, stopped, or failed). */
    private void finishTurn(String answer, String error, String metrics) {
        synchronized (live) { live.setLength(0); }
        if (answer != null && !answer.isEmpty()) {
            history.add(new RemoteChat.Msg("assistant", answer));
            transcript.append(answer).append("\n\n");
        } else if (!history.isEmpty()) {
            // Nothing came back: drop the unanswered user turn so retrying does not duplicate it.
            history.remove(history.size() - 1);
        }
        if (error != null) transcript.append("⚠️ ").append(error).append("\n\n");
        status.setText(metrics);
        setBusy(false);
        render();
    }

    private void clearChat() {
        if (busy) return;
        history.clear();
        transcript.setLength(0);
        status.setText("");
        render();
    }

    private void setBusy(boolean b) {
        busy = b;
        send.setText(b ? "⏹" : "➤");
    }

    private void render() {
        String liveText;
        synchronized (live) { liveText = live.toString(); }
        chat.setText(transcript.toString() + liveText);
        scroll.post(() -> scroll.fullScroll(View.FOCUS_DOWN));
    }

    /** Coalesces streaming updates to roughly one UI refresh per 50 ms. */
    private void scheduleRender() {
        synchronized (renderLock) {
            if (renderScheduled) return;
            renderScheduled = true;
        }
        ui.postDelayed(() -> {
            synchronized (renderLock) { renderScheduled = false; }
            render();
        }, 50);
    }
}
