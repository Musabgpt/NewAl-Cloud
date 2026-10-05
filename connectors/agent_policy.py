"""Stable, packaged behavior profile adapted from the user's uploaded prompt."""
from functools import lru_cache
from pathlib import Path

MARKER = 'MusabAI behavior profile v1'


@lru_cache(maxsize=1)
def profile():
    return MARKER + '\n\n' + Path(__file__).with_name('agent_prompt.md').read_text(encoding='utf-8').strip()


def stale_builtin(text):
    return text.startswith("You are NewAl Code, a coding agent") or (
        text.startswith('MusabAI behavior profile ') and not text.startswith(MARKER + '\n'))
