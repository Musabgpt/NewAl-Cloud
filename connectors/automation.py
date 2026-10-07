"""Agent-accessible provisioning; installation is never substituted for verification."""
import json
from pathlib import Path
import re

from . import tools

NAMES = ['capability_catalog', 'capability_ensure', 'skill_create', 'plugin_install',
         'mcp_registry_search', 'mcp_registry_install']


def _writable(ctx):
    from . import providers
    if getattr(ctx, 'cancel', None) is not None and ctx.cancel.is_set():
        raise providers.Cancelled()
    if getattr(getattr(ctx, 'session', None), 'mode', '') == 'read-only':
        raise tools.ToolError('Read-only mode cannot install capabilities')


def _refresh(ctx):
    from . import extensions
    ctx.skills = extensions.skills(ctx.root)
    agent = getattr(ctx, 'agent', None)
    if agent is not None:
        agent.skills = ctx.skills
        allowed = (getattr(agent, 'agent_def', None) or {}).get('tools')
        if ctx.skills and 'skill' not in agent.session.tool_names and (not allowed or 'skill' in allowed):
            agent.session.tool_names.append('skill')
        agent._schemas = None


@tools.tool('capability_catalog', 'Inspect bundled MCPs, installed skills and bundled plugins before choosing a missing capability.', {}, [], 'read')
def catalog(ctx):
    from . import mcp_bundles, extensions, plugins
    data = {'mcp': mcp_bundles.catalog(ctx.root),
            'skills': [{'name': s['name'], 'description': s['description']} for s in extensions.skills(ctx.root).values()],
            'plugin_marketplaces': plugins.marketplaces()}
    return json.dumps(data, ensure_ascii=False), {'ok': True}


@tools.tool('capability_ensure', 'Install and verify a bundled MCP, start it, and verify live tools/list. Use when its tools are needed for the current task. Never invent credentials or bypass a runtime blocker.',
            {'bundle': tools._s('bundle ID from capability_catalog')}, ['bundle'], 'exec')
def ensure(ctx, bundle):
    from . import mcp_bundles
    _writable(ctx)
    try:
        item = mcp_bundles._item(bundle)
        with mcp_bundles.cancel_scope(getattr(ctx, 'cancel', None)):
            ctx.emit({'type': 'status', 'text': 'Preparing and verifying MCP: ' + item['name']})
            if not mcp_bundles._installed_record(item, ctx.root):
                mcp_bundles.perform(ctx.root, bundle, 'enable')
            mcp_bundles.perform(ctx.root, bundle, 'start')
            result = mcp_bundles.perform(ctx.root, bundle, 'test')
        if result.get('tools', 0) <= 0:
            raise RuntimeError('MCP live verification returned no tools')
        _refresh(ctx)
        return json.dumps(result, ensure_ascii=False), dict(result, ok=True)
    except (ValueError, RuntimeError, OSError, tools.ToolError) as exc:
        raise tools.ToolError(str(exc)) from exc


@tools.tool('skill_create', 'Save an evidence-backed reusable SKILL.md in this project and load it immediately. A skill contains instructions, not a new executable tool or model training.',
            {k: tools._s(v) for k, v in {'name': 'lowercase skill name', 'description': 'when to use it',
             'instructions': 'reusable steps and verification', 'evidence': 'verified result supporting these steps'}.items()},
            ['name', 'description', 'instructions', 'evidence'], 'edit')
def create_skill(ctx, name, description, instructions, evidence):
    _writable(ctx)
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', str(name)):
        raise tools.ToolError('Use a lowercase skill name without paths')
    if any(not isinstance(x, str) or not x.strip() for x in (description, instructions, evidence)):
        raise tools.ToolError('Skill instructions, description and real evidence are required')
    if len(instructions) > 24000 or len(description) > 500 or len(evidence) > 2000:
        raise tools.ToolError('Skill exceeds the bounded instructions size')
    root = Path(ctx.root).resolve()
    directory = root / '.newal' / 'skills' / name
    if directory.is_symlink() or not directory.resolve().is_relative_to(root):
        raise tools.ToolError('Skill path escapes the project')
    path = directory / 'SKILL.md'
    if path.exists() or path.is_symlink():
        raise tools.ToolError('This skill already exists; inspect it before editing')
    directory.mkdir(parents=True, exist_ok=True)
    if hasattr(ctx, 'before_change'):
        ctx.before_change(str(path))
    # JSON strings are valid YAML scalar values and cannot inject front matter.
    body = '---\nname: %s\ndescription: %s\n---\n\n%s\n\nEvidence: %s\n' % (
        json.dumps(name), json.dumps(description, ensure_ascii=False), instructions.strip(), evidence.strip())
    temporary = path.with_suffix('.tmp')
    temporary.write_text(body, encoding='utf-8')
    temporary.replace(path)
    if hasattr(ctx, 'after_change'):
        ctx.after_change(str(path))
    _refresh(ctx)
    return str(path), {'ok': True, 'skill': name}


@tools.tool('plugin_install', 'Install a bundled plugin from the shipped newal marketplace into this project. The packaged plugin brings real commands/skills/hooks; external repository code is not executed by this tool.',
            {'name': tools._s('bundled plugin name from capability_catalog')}, ['name'], 'exec')
def install_plugin(ctx, name):
    from . import plugins
    _writable(ctx)
    markets = [m for m in plugins.marketplaces() if m['name'] == plugins.BUILTIN]
    known = {p['name'] for m in markets for p in m['plugins']}
    if name not in known:
        raise tools.ToolError('Only named plugins from the shipped newal marketplace are supported')
    existing = next((p for p in plugins.listing(ctx.root) if p['name'] == name), None)
    result = existing or plugins.install(name + '@' + plugins.BUILTIN, ctx.root)
    _refresh(ctx)
    return json.dumps(result, ensure_ascii=False), {'ok': True, 'plugin': name}


@tools.tool('mcp_registry_search', 'Discover published MCP Registry entries. Published metadata is untrusted; only compatible verified entries can be installed.',
            {'query': tools._s('capability to discover')}, ['query'], 'read')
def registry_search(ctx, query):
    from . import mcp_registry
    return json.dumps(mcp_registry.search(query), ensure_ascii=False), {'ok': True}


@tools.tool('mcp_registry_install', 'Verify and add a literal HTTPS MCP Registry remote requiring no headers or URL variables. Package commands from registry metadata are never executed.',
            {'name': tools._s('exact published registry server name')}, ['name'], 'exec')
def registry_install(ctx, name):
    from . import mcp_registry
    _writable(ctx)
    try:
        result = mcp_registry.install(ctx.root, name)
        _refresh(ctx)
        return json.dumps(result, ensure_ascii=False), result
    except (ValueError, RuntimeError, OSError) as exc:
        raise tools.ToolError(str(exc)) from exc
