
import argparse
import json
import os
import sys

import common as c

sys.path.insert(0, str(c.ROOT / "src" / "experiment" / "shared"))
import booth_adapter  # noqa: E402


def check_common():
    if not hasattr(c, "ORIENTA_FLAGGED") or "run_meta" not in c.paths("x"):
        raise SystemExit("common.py is out of date (missing ORIENTA_FLAGGED or the run_meta path). "
                         "Replace src/experiment/v2/common.py with the latest version.")


def verify_freeze(P, ignore):
    if ignore:
        return
    if not P["manifest"].exists():
        raise SystemExit("No manifest.json: run `generate.py agents` first (or pass --ignore-freeze).")
    frozen = json.loads(P["manifest"].read_text())["sha256"]
    for k in ("scenarios", "requests", "agent_runs"):
        if c.sha256_file(P[k]) != frozen[k]:
            raise SystemExit(
                f"{k} changed since manifest.json was written. For a pilot, re-run `generate.py agents` "
                "to refresh it. For the main run never edit frozen files (or pass --ignore-freeze and say so)."
            )


def run_booth(P, runs, scs, judges):
    latest = {}
    for r in c.read_jsonl(P["booth"]):
        latest[(r["run_id"], r["judge_model"])] = r
    done = {k for k, v in latest.items() if not v["error"]}
    for judge in judges:
        todo = [r for r in runs if r["agent_model"] != judge and (r["run_id"], judge) not in done]
        print(f"BOOTH judge {judge}: {len(todo)} runs")
        # booth_adapter reads its judge model from this module global (v1 prompt and flagging unchanged)
        booth_adapter._model = judge
        booth_adapter.COMPARATOR_VERSION = f"ollama_judge_v1|{judge}|threshold={booth_adapter.EVIDENCE_THRESHOLD}"
        fails = 0
        for n, run in enumerate(todo, 1):
            rec = {"run_id": run["run_id"], "scenario_id": run["scenario_id"], "agent_model": run["agent_model"],
                   "judge_model": judge, "comparator": booth_adapter.COMPARATOR_VERSION, "ts": c.now_iso()}
            try:
                res = booth_adapter.flag_case(run["agent_claim"], c.evidence_of(scs[run["scenario_id"]]))
                rec.update(flagged=res.flagged, inconclusive=res.inconclusive, status=res.status, reason=res.reason,
                           detail=res.detail, checker_failed=res.checker_failed, score=res.score,
                           judge_note=res.judge_note, error=None)
            except Exception as e:
                rec.update(flagged=None, inconclusive=None, status=None, reason=None, detail=None,
                           checker_failed=None, score=None, judge_note=None, error=f"{type(e).__name__}: {e}")
            c.append_jsonl(P["booth"], rec)
            fails = fails + 1 if rec["error"] else 0
            if fails >= 5:
                raise SystemExit(f"5 BOOTH calls in a row failed ({rec['error']}). Is Ollama running with {judge}?")
            if n % 25 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}")


def run_orienta(P, runs, scs):
    if not os.getenv("ORIENTA_MCP_SERVER_DIR"):
        raise SystemExit('Set ORIENTA_MCP_SERVER_DIR first, e.g. export ORIENTA_MCP_SERVER_DIR="$HOME/Desktop/orienta/mcp-server"')
    import orienta_client

    done = {r["run_id"] for r in c.read_jsonl(P["orienta"]) if not r["error"]}
    todo = [r for r in runs if r["run_id"] not in done]
    print(f"Orienta: {len(todo)} runs")
    cache, fails = {}, 0
    for n, run in enumerate(todo, 1):
        sc = scs[run["scenario_id"]]
        args = dict(objective=sc["objective"], context=c.context_of(sc), proposed_action=run["proposed_action"],
                    domain=sc["domain"], constraints=c.constraints_of(sc))
        key = json.dumps(args, sort_keys=True)
        rec = {"run_id": run["run_id"], "scenario_id": run["scenario_id"], "agent_model": run["agent_model"],
               "cache_hit": key in cache, "ts": c.now_iso()}
        try:
            raw = cache.get(key) or orienta_client.review(**args)
            cache[key] = raw
            decision = raw.get("decision")
            rec.update(decision=decision, flagged=None if decision is None else decision in c.ORIENTA_FLAGGED,
                       reason_codes=raw.get("reason_codes"), reasoning=raw.get("reasoning"),
                       orientation_evidence=raw.get("orientation_evidence"),
                       evaluator_version=raw.get("evaluator_version"),
                       error=None if decision is not None else f"no 'decision' key: {str(raw)[:200]}")
        except orienta_client.OrientaReviewError as e:
            rec.update(decision=None, flagged=None, reason_codes=None, reasoning=None, orientation_evidence=None,
                       evaluator_version=None, error=f"{type(e).__name__}: {e}")
        c.append_jsonl(P["orienta"], rec)
        fails = fails + 1 if rec["error"] else 0
        if fails >= 5:
            raise SystemExit(f"5 Orienta calls in a row failed ({rec['error'][:200]}). "
                             "Check ORIENTA_MCP_SERVER_DIR and that `node server.js` runs there.")
        if n % 25 == 0 or n == len(todo):
            print(f"  {n}/{len(todo)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="pilot")
    ap.add_argument("--scenarios", default=None)
    ap.add_argument("--judges", default=None)
    ap.add_argument("--skip-booth", action="store_true")
    ap.add_argument("--skip-orienta", action="store_true")
    ap.add_argument("--ignore-freeze", action="store_true")
    ap.add_argument("--allow-unlabeled", action="store_true")
    ap.add_argument("--only-labeled", action="store_true")
    a = ap.parse_args()

    check_common()
    P = c.paths(a.tag, a.scenarios)
    verify_freeze(P, a.ignore_freeze)
    scs = {s["id"]: s for s in c.load_scenarios(P["scenarios"])}
    runs = sorted((r for r in c.last_by(c.read_jsonl(P["agent_runs"]), "run_id").values() if r["parse_ok"]),
                  key=lambda r: r["run_id"])
    if not runs:
        raise SystemExit("No parsed agent runs.")
    labels, errs = c.read_labels(P["labels"]) if P["labels"].exists() else ({}, [])
    for e in errs[:5]:
        print(f"WARNING: {e} (that row counts as unlabeled)", file=sys.stderr)
    if a.only_labeled:
        runs = [r for r in runs if r["run_id"] in labels]
        if not runs:
            raise SystemExit("No labeled runs. Label some rows first (label.py go).")
        print(f"--only-labeled: running the {len(runs)} labeled rows only")
    n_labeled = sum(r["run_id"] in labels for r in runs)
    if n_labeled < len(runs) and not a.allow_unlabeled:
        raise SystemExit(f"Only {n_labeled} of {len(runs)} runs are labeled. Label first (see protocol), or pass "
                         "--allow-unlabeled for a plumbing test; analyze.py will then mark results as not blind.")
    judges = a.judges.split(",") if a.judges else c.MODELS
    print(f"{len(runs)} frozen runs, {n_labeled} labeled, judges: {judges}, threshold {booth_adapter.EVIDENCE_THRESHOLD}")

    if not a.skip_booth:
        c.check_models(judges)
        run_booth(P, runs, scs, judges)
    if not a.skip_orienta:
        run_orienta(P, runs, scs)

    old = json.loads(P["run_meta"].read_text()) if P["run_meta"].exists() else {}
    c.write_json(P["run_meta"], {
        "tag": a.tag, "judges": judges, "threshold": booth_adapter.EVIDENCE_THRESHOLD, "total_runs": len(runs),
        "labeled_runs_at_first_start": old.get("labeled_runs_at_first_start", n_labeled),
        "orienta_evaluator_versions": sorted({r["evaluator_version"] for r in c.read_jsonl(P["orienta"])
                                              if r.get("evaluator_version")}),
        "manifest_sha256": json.loads(P["manifest"].read_text())["sha256"] if P["manifest"].exists() else None,
        "provenance": c.provenance(),
    })
    print(f"Done. Next: python src/experiment/v2/analyze.py --tag {a.tag}")


if __name__ == "__main__":
    main()