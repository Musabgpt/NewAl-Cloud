"""Real HTTP/SSE and tool-side-effect regressions for Phase 10 argument loss."""
import json
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from . import tools, providers, agent, session


@contextmanager
def stream_server(events):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            self.server.requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            frames = events(self.server.requests) if callable(events) else events
            body = ''.join('data: ' + json.dumps(e) + '\n\n' for e in frames) + 'data: [DONE]\n\n'
            data = body.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    http.requests = []
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield providers.OpenAICompat('http://127.0.0.1:%d' % http.server_port), http.requests
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def delta(calls, finish=None):
    return {'choices': [{'index': 0, 'delta': {'tool_calls': calls}, 'finish_reason': finish}]}


def part(arguments, name=None, cid=None, index=None):
    call = {'function': {'arguments': arguments}}
    if name is not None: call['function']['name'] = name
    if cid is not None: call['id'] = cid
    if index is not None: call['index'] = index
    return call


class ToolProtocolTests(unittest.TestCase):
    def completion(self, events):
        with stream_server(events) as (api, requests):
            result = api.chat('fixture', [{'role': 'user', 'content': 'create the requested file'}],
                              tools=tools.schemas(['write', 'bash', 'runtime_exec']))
            required = requests[0]['tools'][0]['function']['parameters']['required']
            self.assertIn('content', required)
            return result

    def test_unindexed_continuation_preserves_file_content(self):
        c = self.completion([
            delta([part('{"path":"calculator.html",', 'write', 'w')]),
            delta([part('"content":"<p>حاسبة</p>"}')], 'tool_calls')])
        self.assertEqual(len(c.tool_calls), 1)
        self.assertEqual(json.loads(c.tool_calls[0]['arguments'])['content'], '<p>حاسبة</p>')
        with tempfile.TemporaryDirectory() as root:
            ctx = agent.ToolContext(agent.Agent(session.Session(root)))
            tools.call(ctx, c.tool_calls[0]['name'], c.tool_calls[0]['arguments'])
            self.assertEqual((Path(root) / 'calculator.html').read_text(), '<p>حاسبة</p>')

    def test_id_routes_unindexed_interleaved_commands(self):
        c = self.completion([
            delta([part('{"command":', 'bash', 'a'), part('{"path":"a",', 'write', 'b')]),
            delta([part('"content":"body"}', cid='b'), part('"printf test"}', cid='a')], 'tool_calls')])
        self.assertEqual(len(c.tool_calls), 2)
        self.assertEqual(json.loads(c.tool_calls[0]['arguments']), {'command': 'printf test'})
        self.assertEqual(json.loads(c.tool_calls[1]['arguments']), {'path': 'a', 'content': 'body'})

    def test_repeated_name_and_object_arguments_do_not_corrupt_call(self):
        c = self.completion([
            delta([part({'path': 'a'}, 'write', 'w', 0)]),
            delta([part({'content': 'body'}, 'write', 'w', 0)], 'tool_calls')])
        self.assertEqual(c.tool_calls[0]['name'], 'write')
        self.assertEqual(json.loads(c.tool_calls[0]['arguments']), {'path': 'a', 'content': 'body'})

    def test_final_message_snapshot_replaces_streamed_fragments(self):
        full = part('{"command":"printf done"}', 'bash', 'a')
        c = self.completion([delta([part('{"command":', 'bash', 'a', 0)]),
                             {'choices': [{'index': 0, 'message': {'tool_calls': [full]},
                                           'finish_reason': 'tool_calls'}]}])
        self.assertEqual(len(c.tool_calls), 1)
        self.assertEqual(json.loads(c.tool_calls[0]['arguments']), {'command': 'printf done'})

    def test_ambiguous_continuation_is_rejected_before_execution(self):
        with self.assertRaises(providers.ProviderError):
            self.completion([delta([part('', 'bash', 'a', 0), part('', 'bash', 'b', 1)]),
                             delta([part('{"command":"printf ambiguous"}')], 'tool_calls')])

    def test_standard_indexed_fragments_preserve_repeated_characters(self):
        c = self.completion([delta([part('{"command":"printf ', 'ba', 'a', 0)]),
                             delta([part('ha', 'sh', index=0)]),
                             delta([part('ha"}', index=0)], 'tool_calls')])
        self.assertEqual(c.tool_calls[0]['name'], 'bash')
        self.assertEqual(json.loads(c.tool_calls[0]['arguments']), {'command': 'printf haha'})

    def test_snapshot_without_ids_preserves_distinct_calls(self):
        c = self.completion([{'choices': [{'index': 0, 'message': {'tool_calls': [
            part('{"command":"printf one"}', 'bash'), part('{"path":"a","content":"two"}', 'write')
        ]}, 'finish_reason': 'tool_calls'}]}])
        self.assertEqual([call['name'] for call in c.tool_calls], ['bash', 'write'])
        self.assertEqual(len({call['id'] for call in c.tool_calls}), 2)

    def test_conflicting_identity_is_rejected(self):
        with self.assertRaises(providers.ProviderError):
            self.completion([delta([part('', 'bash', 'a', 0), part('', 'bash', 'b', 1)]),
                             delta([part('{"command":"printf conflict"}', cid='a', index=1)], 'tool_calls')])

    def test_only_first_choice_is_used(self):
        ev = delta([part('{"command":"printf chosen"}', 'bash', 'a', 0)], 'tool_calls')
        ev['choices'].append({'index': 1, 'delta': {'tool_calls': [part('{}', 'write', 'b', 0)]}})
        c = self.completion([ev])
        self.assertEqual(c.tool_calls[0]['name'], 'bash')

    def test_missing_content_is_actionable_and_never_truncates_existing_file(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'calculator.html'
            file.write_text('existing code')
            ctx = agent.ToolContext(agent.Agent(session.Session(root)))
            with self.assertRaises(tools.ToolError) as caught:
                tools.call(ctx, 'write', {'path': 'calculator.html'})
            self.assertIn('required', str(caught.exception))
            self.assertIn('Nothing was executed', str(caught.exception))
            self.assertEqual(file.read_text(), 'existing code')

    def test_nested_arguments_and_aliases_write_real_file(self):
        with tempfile.TemporaryDirectory() as root:
            ctx = agent.ToolContext(agent.Agent(session.Session(root)))
            tools.call(ctx, 'write', {'parameters': {'file_path': 'calculator.html', 'file_content': 'verified body'}})
            self.assertEqual((Path(root) / 'calculator.html').read_text(), 'verified body')

    def test_null_content_rejected_before_file_is_opened(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'a'; file.write_text('keep me')
            ctx = agent.ToolContext(agent.Agent(session.Session(root)))
            with self.assertRaises(tools.ToolError): tools.call(ctx, 'write', {'path': 'a', 'content': None})
            self.assertEqual(file.read_text(), 'keep me')

    def test_explicit_empty_content_is_still_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            ctx = agent.ToolContext(agent.Agent(session.Session(root)))
            tools.call(ctx, 'write', {'path': 'a', 'content': ''})
            self.assertEqual((Path(root) / 'a').read_text(), '')

    def test_missing_command_never_reaches_shell(self):
        ctx = object()
        for name in ('bash', 'runtime_exec'):
            with self.subTest(name=name), patch.object(tools.REGISTRY[name], 'fn') as execute:
                with self.assertRaises(tools.ToolError) as caught: tools.call(ctx, name, {})
                self.assertIn('command', str(caught.exception))
                self.assertIn('required', str(caught.exception))
                execute.assert_not_called()


    def test_agent_repairs_incomplete_write_and_executes_only_corrected_call(self):
        from . import models, provider_pool, settings
        def reply(requests):
            if len(requests) == 1:
                return [delta([part('{"path":"calculator.html"}', 'write', 'bad', 0)], 'tool_calls')]
            if len(requests) == 2:
                feedback = [m['content'] for m in requests[-1]['messages'] if m['role'] == 'tool']
                self.assertTrue(any('Required schema' in text and 'content' in text for text in feedback))
                return [delta([part('{"path":"calculator.html",', 'write', 'good')]),
                        delta([part('"content":"<h1>Verified calculator</h1>"}')], 'tool_calls')]
            return [{'choices': [{'index': 0, 'delta': {'content': 'Created calculator.html.'}, 'finish_reason': 'stop'}]}]
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as home, \
             patch.object(settings, 'HOME', home), stream_server(reply) as (api, requests):
            provider_pool.reset_health()
            client = models.Client({'id': 'argument-fixture', 'provider': 'openai'}, api, 'fixture')
            events = []
            sess = session.Session(root, mode='full-auto')
            runner = agent.Agent(sess, client=client, emit=events.append, persist=False)
            runner.run('Create calculator.html with the requested calculator.', verify=False)
            self.assertEqual((Path(root) / 'calculator.html').read_text(), '<h1>Verified calculator</h1>')
            ends = [e for e in events if e['type'] == 'tool_end']
            self.assertEqual([(e['name'], e['ok']) for e in ends], [('write', False), ('write', True)])
            self.assertTrue(ends[0].get('validation_error'))
            self.assertEqual(len(requests), 3)

    def test_validation_precedes_permission_and_no_placeholder_command_is_run(self):
        from . import circuit
        with tempfile.TemporaryDirectory() as root:
            sess = session.Session(root)
            sess.tool_names = ['bash', 'runtime_exec', 'write']
            runner = agent.Agent(sess, persist=False)
            runner.breaker = circuit.Breaker()
            ctx = agent.ToolContext(runner)
            with patch.object(runner, '_permission') as permission, \
                 patch.object(tools.REGISTRY['bash'], 'fn') as execute:
                result = runner._one_tool(ctx, {'id': 'bad', 'name': 'bash', 'arguments': '{}'}, {})
                self.assertIn('required', result)
                permission.assert_not_called()
                execute.assert_not_called()

    def test_explicit_canonical_fields_win_over_aliases(self):
        with tempfile.TemporaryDirectory() as root:
            ctx = agent.ToolContext(agent.Agent(session.Session(root)))
            tools.call(ctx, 'write', {'path': 'a', 'content': 'real', 'text': 'wrong'})
            self.assertEqual((Path(root) / 'a').read_text(), 'real')


if __name__ == '__main__':
    unittest.main()
