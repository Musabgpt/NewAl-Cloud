import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from . import provider_pool, providers

class ProviderPoolTests(unittest.TestCase):
    def test_skips_unconfigured_free_services_and_keeps_kilo(self):
        c = SimpleNamespace(spec={'id':'nvidia'}, model_name='nvidia', provider=None)
        with patch.dict(os.environ, {}, clear=True):
            ids = [x['id'] for x in provider_pool.candidates(c)]
        self.assertEqual(ids, ['kilo-auto/free'])

    def test_switches_after_overload_and_reports_real_target(self):
        class Bad:
            def chat(self,*a,**k): raise providers.ProviderError('overloaded', 503)
        class Good:
            def chat(self,*a,**k): return 'ok'
        c = SimpleNamespace(spec={'id':'nvidia'}, model_name='nvidia', provider=Bad())
        with patch.object(provider_pool, 'candidates', return_value=[{'id':'backup','model':'backup','base_url':'https://x','provider':'openai'}]), patch.object(provider_pool, 'provider', return_value=Good()):
            self.assertEqual(provider_pool.chat(c, [], tools=[]), 'ok')
        self.assertEqual(c.model_name, 'backup')

