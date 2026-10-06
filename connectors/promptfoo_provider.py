#!/usr/bin/env python3
"""Deterministic Promptfoo provider for MusabAI routing contract evaluation."""
import json
import os
import sys

# CI runs this after connectors/apply.py with PYTHONPATH=desktop.
from newal_code import execution, orchestrator

prompt = sys.argv[1] if len(sys.argv) > 1 else ""
names = {
    "project_rag_search", "memory_recall", "document_engine_selector",
    "browser_tool_selector", "search_router", "searxng_search",
    "termux_exec", "phone", "read", "grep", "bash",
    "execution_plan", "sandbox_exec",
    "git_status", "git_diff", "git_log", "git_commit",
}
payload = {
    "execution": execution.plan(names, prompt),
    "orchestrator": orchestrator.plan(names, prompt),
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
