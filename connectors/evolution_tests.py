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
