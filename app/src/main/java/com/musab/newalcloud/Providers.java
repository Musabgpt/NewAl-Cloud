package com.musab.newalcloud;

final class Providers {
    static final class P {
        final String name, endpoint, model, keyUrl;
        P(String name, String endpoint, String model, String keyUrl) {
            this.name = name;
            this.endpoint = endpoint;
            this.model = model;
            this.keyUrl = keyUrl;
        }
    }

    static final P FREE = new P(
            "FreeLLMAPI • Auto Free",
            "https://api.kilo.ai/api/gateway/chat/completions",
            "kilo-auto/free",
            "");

    static final P[] ALL = { FREE };
    static final String NAME = FREE.name;
    static final String ENDPOINT = FREE.endpoint;
    static final String MODEL = FREE.model;

    static String[] names() {
        return new String[]{FREE.name};
    }

    private Providers() {}
}
