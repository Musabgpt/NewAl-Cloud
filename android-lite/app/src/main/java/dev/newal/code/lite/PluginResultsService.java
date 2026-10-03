package dev.newal.code.lite;

import android.app.IntentService;
import android.content.Intent;
import android.os.Bundle;

/** Receives supported Termux RUN_COMMAND results without exposing credentials to the UI. */
public final class PluginResultsService extends IntentService {
    public static final String EXTRA_EXECUTION_ID = "execution_id";

    public PluginResultsService() {
        super("MusabAI-TermuxResults");
    }

    @Override
    protected void onHandleIntent(Intent intent) {
        if (intent == null) return;
        Bundle result = intent.getBundleExtra("result");
        Termux.setResult(result);
    }
}
