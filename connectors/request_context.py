"""Non-destructive request projection for remote models; disk history stays whole."""
import hashlib
import json
import logging

_LOG = logging.getLogger('newal.request_context')


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def _excerpt(value, limit=1200):
    text = str(value or '')
    if len(text) <= limit:
        return text
    return text[:limit - 250] + '\n[older output omitted; inspect the source again if needed]\n' + text[-200:]


def _tool_summary(group):
    calls = group[0]['tool_calls']
    results = {m.get('tool_call_id'): m.get('content') for m in group[1:]}
    rows = []
    for call in calls:
        function = call.get('function') or {}
        try:
            args = json.loads(function.get('arguments') or '{}')
        except (ValueError, TypeError):
            args = {}
        if not isinstance(args, dict):
            args = {}
        kept = {}
        for key, value in args.items():
            if key in ('content', 'old', 'new', 'patch', 'code') and isinstance(value, str):
                kept[key] = {'omitted_characters':len(value), 'sha256':hashlib.sha256(value.encode()).hexdigest()}
            else:
                kept[key] = _excerpt(value, 500)
        rows.append({'tool':function.get('name'), 'arguments_summary':kept,
                     'recorded_result':_excerpt(results.get(call.get('id')))})
    return {'role':'assistant', 'content':
            '[Historical tool records, not new calls. Full transcript is retained locally. '
            'Source bodies are omitted; read the current files before changing them. '
            'A recorded error is not success.]\n' + json.dumps(rows, ensure_ascii=False)}


def project(spec, messages, definitions=None):
    if spec.get('provider') == 'local' or spec.get('preset') in ('ollama','lmstudio','llamacpp'):
        return messages
    projected = []
    for message in messages:
        if message.get('role') == 'assistant' and spec.get('provider') != 'anthropic':
            message = {k:v for k,v in message.items() if k not in ('reasoning_content','anthropic_blocks')}
        projected.append(message)
    # A working budget, not a claim about the model's tokenizer or capacity.
    # System/user instructions and images are never silently truncated to fit it.
    budget = max(24000, 96000 - _size(definitions or []))
    before = _size(projected)
    if before <= budget:
        return messages if projected == messages else projected
    groups, i = [], 0
    while i < len(projected):
        message = projected[i]
        group = [message]
        i += 1
        if message.get('role') == 'assistant' and message.get('tool_calls'):
            while i < len(projected) and projected[i].get('role') == 'tool':
                group.append(projected[i]); i += 1
        groups.append(group)
    total = before
    for index, group in enumerate(groups):
        if total <= budget:
            break
        calls = group[0].get('tool_calls') or []
        ids = {c.get('id') for c in calls}
        results = {m.get('tool_call_id') for m in group[1:]}
        # Replace whole completed call/result groups, never orphan tool replies.
        if calls and ids == results:
            replacement = [_tool_summary(group)]
        elif len(group) == 1 and group[0].get('role') == 'assistant' and isinstance(group[0].get('content'), str) and len(group[0]['content']) > 6000:
            replacement = [dict(group[0], content='[Excerpt of earlier assistant output]\n' + _excerpt(group[0]['content'], 4000))]
        else:
            continue
        saving = _size(group) - _size(replacement)
        if saving > 0:
            groups[index] = replacement
            total -= saving
    result = [message for group in groups for message in group]
    _LOG.info('remote history projection chars_before=%d chars_after=%d budget=%d', before, _size(result), budget)
    return result
