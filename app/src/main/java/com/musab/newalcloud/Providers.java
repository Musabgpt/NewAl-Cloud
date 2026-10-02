package com.musab.newalcloud;

/**
 * Zero-setup FreeLLMAPI-compatible free router configuration.
 * FreeLLMAPI registers Kilo Gateway as a keyless provider, and Kilo's
 * kilo-auto/free route dynamically selects an available free model.
 */
final class Providers {
    static final String NAME = "FreeLLMAPI • Auto Free";
    static final String ENDPOINT = "https://api.kilo.ai/api/gateway/v1/chat/completions";
    static final String MODEL = "kilo-auto/free";

    private Providers() {}
}
