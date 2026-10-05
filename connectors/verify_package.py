"""Check the engine actually packaged in the APK, rather than only the source checkout."""
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    required = ["agent.py", "tools.py", "server.py", "plugins.py", "addons.py", "mcp.py", "session.py",
                "autonomy.py", "autonomy_tests.py", "connectors.py", "documents.py", "evolution.py", "memory_api.py", "memory_tests.py", "document_tests.py", "evolution_tests.py", "addon_tests.py", "ui/workspace.js", "ui/app.js", "ui/connectors.js", "ui/connectors.css"]
    for path in required:
        assert "newal_code/" + path in archive.namelist(), "Missing packaged feature: " + path
    assert "pypdf/__init__.py" in archive.namelist(), "PDF reader missing from packaged engine"
    for path in ('agent_policy.py', 'agent_prompt.md', 'prompt_tests.py', 'workbench.py', 'workbench_tests.py', 'mcp_config.py', 'mcp_config_tests.py', 'mcp_bundles.py', 'provider_pool.py', 'provider_pool_tests.py', 'ui/mcp_ui.js'):
        assert 'newal_code/' + path in archive.namelist(), 'Prompt feature missing: ' + path
    app = archive.read("newal_code/ui/app.js").decode()
    for anchor in ("open-extensions", "toggle-terminal", "toggle-review", "env-picker", "/api/workspaces"):
        assert anchor in app, "Original UI feature missing: " + anchor
    assert "connectors.js" in archive.read("newal_code/ui/index.html").decode()
    assert "MUSAB_CONNECTORS_V1" in archive.read("newal_code/tools.py").decode()
print("Packaged original features and connectors verified")

