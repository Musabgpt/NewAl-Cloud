"""Is a change really better? The coding test run k times with the same model (item 6 of the research plan).

One success says little: a free model that solves a task now and then fails it often, and the same request goes to a
different model from one provider to the next. tau-bench measures that with pass^k, the share of tasks solved in all k
tries, beside pass@1, the average success of one try. `newal-code bench --repeat 3` prints both, and each task's
count, so two versions of the app are compared on what holds, not on one lucky run.
"""
from . import benchmark


def summarize(results, k):
    """{"tasks": {id: {"passed", "tries"}}, "pass@1", "pass^k"} of benchmark results (k tries of each task)."""
    by = {}
    for r in results:
        by.setdefault(r["id"], []).append(bool(r.get("ok")))
    tasks = {tid: {"passed": sum(oks), "tries": len(oks)} for tid, oks in by.items()}
    n = len(tasks)
    pass1 = sum(t["passed"] / float(t["tries"]) for t in tasks.values()) / n if n else 0.0
    passk = sum(1 for t in tasks.values() if t["passed"] == t["tries"]) / float(n) if n else 0.0
    return {"tasks": tasks, "pass@1": round(pass1, 3), "pass^%d" % k: round(passk, 3), "repeat": k}


def run(model="auto", ids=None, k=3, log=print, client=None):
    """The benchmark k times over one connection to the model; the summary with every try's record."""
    from . import models
    spec = models.resolve(model)
    client = client or models.connect(spec)
    results = []
    for i in range(k):
        log("try %d of %d" % (i + 1, k))
        for r in benchmark.run(model, ids, log=log, client=client)["results"]:
            r["try"] = i + 1
            results.append(r)
    out = summarize(results, k)
    out.update({"program": "NewAl Code", "model": spec["id"], "seconds": round(sum(r["seconds"] for r in results), 1),
                "results": results})
    return out


def line(summary):
    k = summary["repeat"]
    tasks = " ".join("%s %d/%d" % (tid, t["passed"], t["tries"]) for tid, t in sorted(summary["tasks"].items()))
    return "TOTAL %.1f s, pass@1 %.0f%%, pass^%d %.0f%% (%s)" % (
        summary["seconds"], 100 * summary["pass@1"], k, 100 * summary["pass^%d" % k], tasks)
