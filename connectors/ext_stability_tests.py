"""The coding test's stability over k tries (stability.py): pass@1, pass^k, and `bench --repeat`."""
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock


class StabilityTests(unittest.TestCase):
    def test_pass_at_1_and_pass_hat_k(self):
        from . import stability
        rs = [{"id": "a", "ok": True}, {"id": "a", "ok": True}, {"id": "b", "ok": True}, {"id": "b", "ok": False}]
        s = stability.summarize(rs, 2)
        self.assertEqual(s["tasks"], {"a": {"passed": 2, "tries": 2}, "b": {"passed": 1, "tries": 2}})
        self.assertEqual((s["pass@1"], s["pass^2"]), (0.75, 0.5))

    def test_the_benchmark_runs_k_times_on_one_connection(self):
        from . import benchmark, models, stability
        client, seen = object(), []

        def run(model, ids, log=print, client=None):
            seen.append(client)
            ok = len(seen) != 2                                      # task y fails on the second try
            return {"results": [{"id": "x", "ok": True, "seconds": 1.0}, {"id": "y", "ok": ok, "seconds": 2.0}]}
        with mock.patch.object(models, "resolve", return_value={"id": "free-model"}), \
                mock.patch.object(models, "connect", return_value=client), \
                mock.patch.object(benchmark, "run", side_effect=run):
            s = stability.run("auto", None, 3, log=lambda *a: None)
        self.assertEqual(seen, [client] * 3)
        self.assertEqual((s["pass@1"], s["pass^3"]), (round(5 / 6.0, 3), 0.5))
        self.assertEqual(stability.line(s), "TOTAL 9.0 s, pass@1 83%, pass^3 50% (x 3/3 y 2/3)")
        out = io.StringIO()
        with mock.patch.object(stability, "run", return_value=s), redirect_stdout(out):
            self.assertEqual(benchmark.main(["--repeat", "3"]), 0)
        self.assertIn("pass^3 50%", out.getvalue())
