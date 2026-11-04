
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Sequence

import booth


OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://localhost:11434",
).rstrip("/")

if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST

EVIDENCE_THRESHOLD = 0.7

_model: Optional[str] = None
_last_why: Optional[str] = None
COMPARATOR_VERSION = "ollama_judge_v1|<model not resolved yet>"

_SYSTEM = (
    "You are a strict evidence checker. You are given EVIDENCE (source facts) "
    "and a CLAIM. Judge only whether the evidence supports the claim as "
    "stated. Do not use outside knowledge."
)

_USER_TEMPLATE = """EVIDENCE:
{evidence}

CLAIM:
{claim}

Score how well the evidence supports the claim, from 0.0 to 1.0:
- 0.0 to 0.2: the evidence contradicts the claim
- 0.3 to 0.6: the evidence does not establish the claim (missing, hedged, or overstated)
- 0.7 to 1.0: the evidence directly supports the claim
Facts in the evidence that are irrelevant to the claim do not lower the score.

Respond with ONLY a JSON object: {{"score": <number>, "why": "<one short sentence>"}}"""


def _http(path: str, body: Optional[dict] = None, timeout: int = 180) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_HOST + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Ollama HTTP {e.code}: "
            f"{e.read().decode('utf-8', 'replace')[:300]}"
        )
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_HOST}: {e.reason}"
        )


def ensure_ready() -> str:
    global _model, COMPARATOR_VERSION

    if _model:
        return _model

    try:
        tags = _http("/api/tags", timeout=10)
    except RuntimeError as e:
        raise SystemExit(
            f"{e}\n"
            "Start Ollama (open the app or run `ollama serve`) and retry."
        )

    installed = [m["name"] for m in tags.get("models", [])]

    if not installed:
        raise SystemExit(
            "Ollama is running but has no models. "
            "Run `ollama list` / `ollama pull <model>` once."
        )

    wanted = os.getenv("OLLAMA_MODEL", "").strip()

    if wanted:
        if wanted not in installed:
            raise SystemExit(
                f"Model {wanted!r} is not installed. Installed: {installed}"
            )
        _model = wanted
    elif len(installed) == 1:
        _model = installed[0]
    else:
        raise SystemExit(
            "Several models are installed; choose one:\n  "
            + "\n  ".join(installed)
            + "\nThen: export OLLAMA_MODEL=<name>"
        )

    COMPARATOR_VERSION = (
        f"ollama_judge_v1|{_model}|threshold={EVIDENCE_THRESHOLD}"
    )

    print(f"Ollama judge model: {_model}", file=sys.stderr)

    return _model


def ollama_compare_fn(
    answer: str,
    evidence: Sequence[str],
) -> float:
    global _last_why

    ev = "\n".join(f"- {e}" for e in evidence)

    data = _http(
        "/api/chat",
        {
            "model": ensure_ready(),
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _USER_TEMPLATE.format(
                        evidence=ev,
                        claim=answer,
                    ),
                },
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "num_predict": 1000,
            },
        },
    )

    text = (data.get("message", {}).get("content") or "").strip()
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL,
    ).strip()

    m = re.search(r"\{.*\}", text, re.DOTALL)

    if not m:
        raise ValueError(
            f"judge returned no JSON: {text[:200]!r}"
        )

    obj = json.loads(m.group(0))
    _last_why = str(obj.get("why", ""))[:300] or None

    return float(obj["score"])


@dataclass
class BoothFlagResult:
    flagged: bool
    inconclusive: bool
    status: str
    reason: Optional[str]
    detail: Optional[str]
    checker_failed: bool
    score: Optional[float]
    judge_note: Optional[str]
    comparator: str


def flag_case(
    agent_claim: str,
    evidence: Sequence[str],
    compare_fn=None,
) -> BoothFlagResult:
    global _last_why

    _last_why = None
    fn = compare_fn or ollama_compare_fn

    result = booth.check_with_evidence(
        answer=agent_claim,
        evidence=list(evidence),
        compare_fn=fn,
        evidence_threshold=EVIDENCE_THRESHOLD,
    )

    return BoothFlagResult(
        flagged=result.status == booth.BLOCKED,
        inconclusive=result.status == booth.UNCERTAIN,
        status=result.status,
        reason=result.reason,
        detail=result.detail,
        checker_failed=result.checker_failed,
        score=result.evidence_agreement,
        judge_note=_last_why,
        comparator=COMPARATOR_VERSION,
    )
