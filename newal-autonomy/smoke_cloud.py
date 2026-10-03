#!/usr/bin/env python3
"""End-to-end smoke test for MusabAI's standalone Cloud session.

It deliberately uses a directory with NO .git metadata and exercises:
  Kilo Auto Free -> Action #43 Service/Agent -> file tool -> verification.
"""
import json
import os
import tempfile
import time
import urllib.request

HOME = tempfile.mkdtemp(prefix="musabai-cloud-smoke-")
os.environ["HOME"] = HOME
os.environ["NEWAL_SERVER_KEY"] = "smoke-key-0123456789abcdef"
os.environ["PYTHONPATH"] = os.path.abspath("desktop")

cfg = os.path.join(HOME, ".newal-code")
os.makedirs(cfg, exist_ok=True)
with open(os.path.join(cfg, "config.json"), "w", encoding="utf-8") as f:
    json.dump({
        "model": "kilo-auto/free",
        "models": {"kilo-auto/free": {
            "id":"kilo-auto/free","name":"Auto Free","provider":"openai",
            "base_url":"https://api.kilo.ai/api/gateway","model":"kilo-auto/free",
            "api_key":"","context":256000}},
        "mode":"auto-edit","verify":True,"test_after_edit":True,"auto_context":True,"web":True
    }, f)

from newal_code import server

httpd, _ = server.serve(0, open_browser=False)
import threading
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % httpd.server_address[1]
headers = {"Authorization":"Bearer smoke-key-0123456789abcdef","Content-Type":"application/json"}

def call(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base+path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

try:
    # The workspace endpoint must succeed without Git.
    w = call("POST", "/api/cloud/workspace", {"title":"Cloud smoke"})
    root = w["root"]
    assert not os.path.exists(os.path.join(root, ".git")), "cloud workspace unexpectedly requires git"

    # The normal Action #43 session API must accept the standalone workspace.
    sid = call("POST", "/api/sessions", {
        "root":root,"model":"kilo-auto/free","mode":"auto-edit","worktree":False,"warm":False
    })["id"]

    call("POST", "/api/sessions/%s/send" % sid, {
        "text":"Create a file named smoke.txt containing exactly SMOKE_OK. Then verify the file exists and report the result.",
        "lang":"en"
    }, timeout=30)

    deadline = time.time() + 180
    while time.time() < deadline:
        p = os.path.join(root, "smoke.txt")
        if os.path.isfile(p):
            text = open(p, encoding="utf-8").read().strip()
            if text == "SMOKE_OK":
                print("CLOUD_SMOKE_OK", sid)
                break
        time.sleep(2)
    else:
        raise SystemExit("cloud session did not create/verify smoke.txt within 180s")
finally:
    httpd.shutdown()
