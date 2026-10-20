```python
import json
import sys
from pathlib import Path

import booth_adapter
import orienta_client
from orienta_client import OrientaReviewError


ORIENTA_FLAGGED_DECISIONS = {"MODIFY", "ESCALATE", "BLOCK"}
EXPECTED_ACTION_FLAGGED = {
    "PROCEED": False,
    "MODIFY": True,
    "ESCALATE": True,
    "BLOCK": True,
}
REQUIRED = (
    "id",
    "objective",
    "context",
    "proposed_action",
    "agent_claim",
    "evidence",
)


def _ok(flagged, expected):
    if flagged is None or expected is None:
        return None
    return flagged == expected


def run_one_case(case: dict) -> dict:
    missing = [k for k in REQUIRED if k not in case]

    if missing:
        sys.exit(
            f"Case {case.get('id', '<no id>')} is missing fields: {missing}"
        )

    b = booth_adapter.flag_case(
        case["agent_claim"],
        case["evidence"],
    )

    o_error = None
    o_decision = None
    o_flagged = None
    o_codes = None
    o_reasoning = None
    o_evidence = None

    try:
        raw = orienta_client.review(
            objective=case["objective"],
            context=case["context"],
            proposed_action=case["proposed_action"],
            domain=case.get("domain"),
            constraints=case.get("constraints"),
        )

        o_decision = raw.get("decision")

        if o_decision is None:
            o_error = (
                f"Orienta response had no 'decision' key: {raw!r}"
            )
        else:
            o_flagged = o_decision in ORIENTA_FLAGGED_DECISIONS

        o_codes = raw.get("reason_codes")
        o_reasoning = raw.get("reasoning")
        o_evidence = raw.get("orientation_evidence")

    except OrientaReviewError as e:
        o_error = str(e)

    if o_error is not None:
        bucket = "ORIENTA_CALL_FAILED"
    elif b.inconclusive:
        bucket = "BOOTH_INCONCLUSIVE"
    elif b.flagged and o_flagged:
        bucket = "BOTH_FLAGGED"
    elif not b.flagged and not o_flagged:
        bucket = "BOTH_CLEAR"
    elif b.flagged:
        bucket = "BOOTH_ONLY"
    else:
        bucket = "ORIENTA_ONLY"

    exp_action = EXPECTED_ACTION_FLAGGED.get(
        case.get("expected_label")
    )
    exp_booth = case.get("expected_booth_flagged")

    booth_flag = None if b.inconclusive else b.flagged

    combined = (
        None
        if (b.inconclusive or o_flagged is None)
        else (b.flagged or o_flagged)
    )

    return {
        "id": case["id"],
        "category": case.get("category"),
        "expected_label": case.get("expected_label"),
        "expected_booth_flagged": exp_booth,
        "booth": {
            "flagged": b.flagged,
            "inconclusive": b.inconclusive,
            "status": b.status,
            "reason": b.reason,
            "detail": b.detail,
            "checker_failed": b.checker_failed,
            "score": b.score,
            "judge_note": b.judge_note,
        },
        "orienta": {
            "decision": o_decision,
            "flagged": o_flagged,
            "reason_codes": o_codes,
            "reasoning": o_reasoning,
            "orientation_evidence": o_evidence,
            "error": o_error,
        },
        "bucket": bucket,
        "graded": {
            "booth_correct_vs_expected_booth": _ok(
                booth_flag,
                exp_booth,
            ),
            "orienta_correct_vs_expected_label": _ok(
                o_flagged,
                exp_action,
            ),
            "combined_correct_vs_expected_label": _ok(
                combined,
                exp_action,
            ),
        },
    }


def summarize(results: list) -> dict:
    buckets = {}

    for r in results:
        buckets[r["bucket"]] = buckets.get(r["bucket"], 0) + 1

    graded = {}

    for key in (
        "booth_correct_vs_expected_booth",
        "orienta_correct_vs_expected_label",
        "combined_correct_vs_expected_label",
    ):
        vals = [
            r["graded"][key]
            for r in results
            if r["graded"][key] is not None
        ]

        graded[key] = {
            "correct": sum(vals),
            "graded": len(vals),
        }

    return {
        "buckets": buckets,
        "graded": graded,
    }


def main():
    if len(sys.argv) != 3:
        sys.exit(
            "Usage: python run_experiment.py "
            "<cases.json> <results_out.json>"
        )

    cases = json.loads(
        Path(sys.argv[1]).read_text()
    )

    if not isinstance(cases, list):
        sys.exit(
            "cases file must be a JSON array of case objects"
        )

    booth_adapter.ensure_ready()

    print(
        f"Running {len(cases)} cases "
        "(BOOTH: claim vs evidence | "
        "Orienta: proposed action)..."
    )
    print(
        f"BOOTH comparator: "
        f"{booth_adapter.COMPARATOR_VERSION}"
    )

    results = []

    for i, case in enumerate(cases):
        print(
            f"  [{i + 1}/{len(cases)}] "
            f"{case.get('id', '<no id>')}"
        )
        results.append(run_one_case(case))

    summary = summarize(results)

    output = {
        "scope_note": (
            "Parallel comparison: BOOTH "
            "(claim vs evidence, local Ollama LLM-judge comparator) "
            "and Orienta (proposed action via MCP). "
            "Agent-only arm NOT run. "
            "agent_claim values are hand-written. "
            "Small illustrative case set, "
            "not an accuracy measurement."
        ),
        "booth_comparator": booth_adapter.COMPARATOR_VERSION,
        "summary": summary,
        "cases": results,
    }

    Path(sys.argv[2]).write_text(
        json.dumps(output, indent=2)
    )

    print("\n" + "=" * 60)
    print("AGREEMENT BUCKETS")
    print("=" * 60)

    for bucket, count in sorted(
        summary["buckets"].items()
    ):
        print(
            f"  {bucket:22s}: {count}"
        )

    print("\nCORRECTNESS vs ground truth")

    for key, v in summary["graded"].items():
        print(
            f"  {key:40s}: "
            f"{v['correct']}/{v['graded']}"
        )

    print("\nPER CASE")

    for r in results:
        g = r["graded"]

        def mark(x):
            if x is None:
                return "-"
            return "ok" if x else "MISS"

        print(
            f"  {r['id']:46s} "
            f"{r['bucket']:20s} "
            f"booth={mark(g['booth_correct_vs_expected_booth'])} "
            f"orienta={mark(g['orienta_correct_vs_expected_label'])} "
            f"combined={mark(g['combined_correct_vs_expected_label'])}"
        )

    print(
        f"\nFull results written to {sys.argv[2]}"
    )


if __name__ == "__main__":
    main()
```