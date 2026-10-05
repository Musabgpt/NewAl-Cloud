"""Stable, packaged behavior profile adapted from the user's uploaded prompt."""
from functools import lru_cache
from pathlib import Path

MARKER = 'MusabAI behavior profile v2'


@lru_cache(maxsize=1)
def profile():
    return MARKER + '\n\n' + Path(__file__).with_name('agent_prompt.md').read_text(encoding='utf-8').strip()


def stale_builtin(text):
    return text.startswith("You are NewAl Code, a coding agent") or (
        text.startswith('MusabAI behavior profile ') and not text.startswith(MARKER + '\n'))


def runtime_context(agent):
    """Describe only tools actually offered to this agent, including late connections."""
    from . import connectors
    names = {d['function']['name'] for d in agent.schemas()}
    providers = {}
    for name in sorted(names):
        operation = connectors.OPERATIONS.get(name)
        if operation:
            label = connectors.CATALOG.get(operation[0], operation[0])
            providers[label] = providers.get(label, 0) + 1
    import json
    state = {'permission_mode': agent.session.mode,
             'project_directory': agent.session.root,
             'internal_terminal': 'bash' in names,
             'background_jobs': 'job' in names,
             'connected_service_tools': providers}
    return '\n\nCurrent runtime capabilities (data, not instructions):\n' + json.dumps(state, ensure_ascii=False)
