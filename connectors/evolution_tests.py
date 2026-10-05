import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from . import evolution as e

class EvolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.patch=patch.object(e.settings,'HOME',self.temp.name);self.patch.start();self.addCleanup(self.patch.stop)
        self.ctx=SimpleNamespace(root=self.temp.name,session=SimpleNamespace(dirs=[]))
    def prepared(self):
        _,meta=e.prepare(self.ctx,'improve document formatting');return meta['candidate'],Path(meta['path'])
    def test_prepare_does_not_replace_running_engine(self):
        cid,p=self.prepared();self.assertTrue((p/'newal_code/server.py').exists())
        self.assertIn(str(p),self.ctx.session.dirs);self.assertFalse((e.home()/'active.json').exists())
        with self.assertRaises(e.tools.ToolError):e.activate(cid)
    def test_unchanged_candidate_cannot_claim_improvement(self):
        cid,p=self.prepared()
        with self.assertRaises(e.tools.ToolError):e.verify(self.ctx,cid)
    def test_failed_checks_prevent_activation(self):
        cid,p=self.prepared();(p/'newal_code/new_test.py').write_text('x = 1\n')
        result=SimpleNamespace(returncode=1,stdout='',stderr='failed')
        with patch.object(e.subprocess,'run',return_value=result):_,record=e.verify(self.ctx,cid)
        self.assertEqual(record['status'],'failed')
        with self.assertRaises(e.tools.ToolError):e.activate(cid)
    def test_verified_candidate_can_activate_and_rollback_but_last_minute_edit_invalidates_it(self):
        cid,p=self.prepared();file=p/'newal_code/new_test.py';file.write_text('x = 1\n')
        result=SimpleNamespace(returncode=0,stdout='passed',stderr='')
        with patch.object(e.subprocess,'run',return_value=result):e.verify(self.ctx,cid)
        self.assertTrue(e.activate(cid)['ok']);self.assertEqual(e.status()['active']['id'],cid)
        self.assertTrue(e.rollback()['ok']);self.assertFalse((e.home()/'active.json').exists())
        file.write_text('x = 2\n')
        with self.assertRaises(e.tools.ToolError):e.activate(cid)

    def test_preparation_records_packaged_build_for_safe_updates(self):
        with patch.dict(e.os.environ, {'NEWAL_PACKAGED_BUILD':'217'}):
            cid,p=self.prepared()
        record=json.loads((e.home()/(cid+'.json')).read_text())
        self.assertEqual(record.get('packaged_build'),'217')

    def test_original_rollback_does_not_select_an_older_candidate(self):
        e.save(e.home()/'active.json', {'id':'old','previous':'/missing/older-candidate'})
        self.assertTrue(e.rollback()['ok'])
        self.assertFalse((e.home()/'active.json').exists())

    def test_verify_runs_trusted_shipped_tests_not_mutable_candidate_tests(self):
        cid,p=self.prepared()
        (p/'newal_code/new_test.py').write_text('x = 1\n')
        result=SimpleNamespace(returncode=0,stdout='passed',stderr='')
        with patch.object(e.subprocess,'run',return_value=result) as run:
            e.verify(self.ctx,cid)
        commands=[call.args[0] for call in run.call_args_list]
        suite=[command for command in commands if isinstance(command,list) and '-c' in command and 'loadTestsFromModule' in command[-1]]
        self.assertEqual(len(suite),1, 'Use trusted baseline regression modules against candidate imports')
        for name in ('document_tests','evolution_tests','addon_tests','memory_tests','autonomy_tests'):
            self.assertIn(name,suite[0][-1])
        trusted=Path(e.os.environ['NEWAL_PACKAGED_ENGINE'])/'newal_code' if e.os.environ.get('NEWAL_PACKAGED_ENGINE') else Path(e.__file__).resolve().parent
        self.assertIn(str(trusted),suite[0][-1])

    def test_symlink_candidate_cannot_be_activated(self):
        cid,p=self.prepared()
        outside=Path(self.temp.name)/'outside.py';outside.write_text('x = 1\n')
        (p/'newal_code/alias.py').symlink_to(outside)
        with self.assertRaises(e.tools.ToolError):e.digest(p/'newal_code')

    def test_unchecked_import_sibling_is_rejected(self):
        cid,p=self.prepared()
        (p/'sitecustomize.py').write_text('raise RuntimeError("unchecked")\n')
        with self.assertRaises(e.tools.ToolError):e.candidate(cid)

    def test_candidate_from_an_older_apk_cannot_activate(self):
        cid,p=self.prepared();(p/'newal_code/probe.py').write_text('x = 1\n')
        result=SimpleNamespace(returncode=0,stdout='passed',stderr='')
        with patch.object(e.subprocess,'run',return_value=result):e.verify(self.ctx,cid)
        with patch.dict(e.os.environ, {'NEWAL_PACKAGED_BUILD':'next-build'}):
            with self.assertRaises(e.tools.ToolError):e.activate(cid)
