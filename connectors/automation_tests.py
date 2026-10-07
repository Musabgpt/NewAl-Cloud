"""Autonomous provisioning uses real registry operations and truthful verification."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from . import tools, settings, extensions, plugins, mcp_bundles, mcp_config


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.patch = mock.patch.object(settings, 'HOME', self.root + '/private')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.ctx = SimpleNamespace(root=self.root, cancel=threading.Event(), session=SimpleNamespace(
            mode='full-auto', dirs=[], tool_names=[], root=self.root), emit=lambda ev: None)

    def invoke(self, tool_name, **args):
        self.assertTrue(tool_name in tools.REGISTRY, 'agent cannot provision ' + tool_name + ' yet')
        return tools.REGISTRY[tool_name].fn(self.ctx, **args)

    def test_new_skill_is_discovered_without_restarting_session(self):
        text, meta = self.invoke('skill_create', name='browser-check', description='Verify a browser task',
            instructions='Read the actual page title before reporting success.', evidence='Validated with browser tools')
        self.assertTrue(meta['ok'])
        self.assertIn('browser-check', extensions.skills(self.root))
        self.assertIn('actual page title', extensions.skills(self.root)['browser-check']['body'])
        with self.assertRaises(tools.ToolError):
            self.invoke('skill_create', name='../escape', description='bad', instructions='bad', evidence='bad')
        self.assertFalse((Path(self.root).parent / 'escape').exists())

    def test_first_skill_becomes_callable_in_existing_agent_session(self):
        from . import agent, session, automation
        s = session.Session(self.root)
        a = agent.Agent(s, client=SimpleNamespace(spec={}, local=False, on_device=False))
        self.addCleanup(a.memory.close)
        a.schemas()
        self.assertNotIn('skill', s.tool_names)
        ctx = agent.ToolContext(a)
        automation.create_skill(ctx, 'verified-loop', 'Use a verified loop', 'Inspect, repair, test.', 'Passing project test')
        self.assertIn('skill', {d['function']['name'] for d in a.schemas()})

    def test_bundled_plugin_is_installed_into_project_without_git_or_shell(self):
        self.invoke('plugin_install', name='data')
        self.assertTrue(any(p['name'] == 'data' for p in plugins.listing(self.root)))
        self.invoke('plugin_install', name='data')  # idempotent provisioning
        with self.assertRaises(tools.ToolError):
            self.invoke('plugin_install', name='https://unreviewed.example/code')

    def test_mcp_ensure_verifies_before_persisting_and_starts_process(self):
        ready = {'runtime': 'LOCAL_HOST', 'missing': [], 'unknown': [], 'stdio': True, 'reason': 'host'}
        class Server:
            tools = [{'name': 'read_graph'}]
            def __init__(self, *args): pass
            def start(self, **kwargs): return self
            def stop(self): pass
            def alive(self): return True
            def _list_tools(self): return self.tools
        with mock.patch.object(mcp_bundles, '_runtime_requirements', return_value=ready), \
             mock.patch.object(mcp_config, 'StdioServer', Server):
            _, meta = self.invoke('capability_ensure', bundle='memory')
        self.assertTrue(meta['ok'])
        self.assertGreater(mcp_config.read(self.root)['memory']['tools'], 0)
        mcp_bundles._RUNNING.clear()

    def test_mcp_failure_cannot_be_saved_as_installed(self):
        with mock.patch.object(mcp_bundles, '_test', side_effect=RuntimeError('initialize failed')):
            with self.assertRaisesRegex(tools.ToolError, 'initialize failed'):
                self.invoke('capability_ensure', bundle='memory')
        self.assertNotIn('memory', mcp_config.read(self.root))

    def test_cancelled_preparation_cannot_start_or_install_anything(self):
        self.ctx.cancel.set()
        with mock.patch.object(mcp_bundles, 'perform') as perform:
            with self.assertRaises(Exception):
                self.invoke('capability_ensure', bundle='memory')
            perform.assert_not_called()

    def test_read_only_mode_cannot_install_capabilities(self):
        self.ctx.session.mode='read-only'
        with self.assertRaises(tools.ToolError):
            self.invoke('plugin_install', name='data')
        self.assertEqual(plugins.listing(self.root), [])
