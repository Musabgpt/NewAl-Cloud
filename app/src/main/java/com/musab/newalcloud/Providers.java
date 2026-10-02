package com.musab.newalcloud;

/** Presets for OpenAI-compatible chat endpoints. Model names change often; they stay editable in the UI. */
final class Providers {
    static final class P {
        final String name, endpoint, model, keyUrl;
        P(String name, String endpoint, String model, String keyUrl) {
            this.name = name; this.endpoint = endpoint; this.model = model; this.keyUrl = keyUrl;
        }
    }

    static final P[] ALL = {
            new P("Groq", "https://api.groq.com/openai/v1/chat/completions",
                    "llama-3.3-70b-versatile", "console.groq.com/keys"),
            new P("Google AI Studio (Gemini)", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    "gemini-2.5-flash", "aistudio.google.com/apikey"),
            new P("Cerebras", "https://api.cerebras.ai/v1/chat/completions",
                    "llama-3.3-70b", "cloud.cerebras.ai"),
            new P("OpenRouter (free models)", "https://openrouter.ai/api/v1/chat/completions",
                    "meta-llama/llama-3.3-70b-instruct:free", "openrouter.ai/keys"),
            new P("Mistral", "https://api.mistral.ai/v1/chat/completions",
                    "mistral-small-latest", "console.mistral.ai"),
            new P("Custom", "", "", ""),
    };

    static String[] names() {
        String[] n = new String[ALL.length];
        for (int i = 0; i < ALL.length; i++) n[i] = ALL[i].name;
        return n;
    }

    private Providers() {}
}
