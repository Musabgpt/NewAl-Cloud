"""The coding test, k times over: `newal-code bench --repeat k` prints pass@1 and pass^k (stability.py)."""
import shutil


def apply(src, package, replace):
    for name in ("stability.py", "ext_stability_tests.py"):
        shutil.copyfile(src / name, package / name)
    bm = package / "benchmark.py"
    replace(bm, '    ap.add_argument("--out", default="")\n',
            '    ap.add_argument("--out", default="")\n'
            '    ap.add_argument("--repeat", type=int, default=1, help="each task this many times: pass@1 and pass^k")\n')
    replace(bm, '    summary = run(a.model, a.tasks)\n'
                '    print("TOTAL %.1f s, %d/%d passed" % (summary["seconds"], summary["passed"], summary["tasks"]))\n',
            '    if a.repeat > 1:\n'
            '        from . import stability\n'
            '        summary = stability.run(a.model, a.tasks, a.repeat)\n'
            '        print(stability.line(summary))\n'
            '    else:\n'
            '        summary = run(a.model, a.tasks)\n'
            '        print("TOTAL %.1f s, %d/%d passed" % (summary["seconds"], summary["passed"], summary["tasks"]))\n')
    with open(package / "claude_parity_tests.py", "a", encoding="utf-8") as f:
        f.write("\nfrom .ext_stability_tests import StabilityTests  # noqa: E402,F401 - run with the parity tests in CI\n")
