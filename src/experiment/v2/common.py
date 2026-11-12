"""Shared constants, paths, helpers, Ollama chat, and scenario/label validation for v2."""
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

MODELS = ["llama3.1:8b", "qwen2.5-coder:7b", "qwen2.5:7b-instruct"]
STYLES = ["typos_slang", "vague", "multi_request", "pressure_unverified"]
WRITER_TEMPERATURE = 0.9
AGENT_TEMPERATURE = 0.7
VARIANTS = 4
QUADRANT_QUOTA = 20

EDGE_TYPES = [
    "boundary", "cumulative", "policy_conflict", "reworded", "authority_claim",
    "third_party_consented", "third_party_unauthorized", "sensitive_data",
    "conflicting_facts", "control",
]
CLAIM_LABELS = ("SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "MIXED", "EXCLUDE")
ACTION_LABELS = ("PROCEED", "MODIFY", "ESCALATE", "BLOCK", "EXCLUDE")
RISKY_LABELS = ("MODIFY", "ESCALATE", "BLOCK")
ORIENTA_FLAGGED = {"MODIFY", "ESCALATE", "BLOCK"}

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST


def paths(tag, scenarios=None):
    d, r = ROOT / "data" / "v2", ROOT / "results" / "v2"
    return {
        "scenarios": Path(scenarios) if scenarios else d / "scenarios.json",
        "requests": d / tag / "requests.jsonl",
        "agent_runs": d / tag / "agent_runs.jsonl",
        "manifest": d / tag / "manifest.json",
        "labels": d / tag / "labels.csv",
        "booth": r / tag / "booth.jsonl",
        "orienta": r / tag / "orienta.jsonl",
        "run_meta": r / tag / "run_meta.json",
        "summary": r / tag / "summary.json",
    }


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slug(model):
    return re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-")


def seed_for(*parts):
    return zlib.crc32("|".join(parts).encode("utf-8")) & 0x7FFFFFFF


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def last_by(records, key):
    out = {}
    for r in records:
        out[r[key]] = r
    return out


def evidence_of(sc):
    return sc["facts"] + sc["policy"]


def context_of(sc):
    return " ".join(sc["facts"])


def constraints_of(sc):
    return list(sc["policy"])


_FIELDS = ("id", "edge_type", "domain", "objective", "user_request", "facts", "policy", "answer_key")


def validate_scenarios(scs):
    errs, seen = [], set()
    if not isinstance(scs, list) or not scs:
        return ["scenario file must be a non-empty JSON array"]
    for i, s in enumerate(scs):
        t = f"[{i}] {s.get('id', '<no id>')}"
        errs += [f"{t}: missing {k!r}" for k in _FIELDS if k not in s]
        for k in ("facts", "policy"):
            if k in s and not (isinstance(s[k], list) and all(isinstance(x, str) for x in s[k])):
                errs.append(f"{t}: {k!r} must be a list of strings")
        if "facts" in s and not s["facts"]:
            errs.append(f"{t}: facts must not be empty")
        if s.get("edge_type") not in EDGE_TYPES:
            errs.append(f"{t}: edge_type must be one of {EDGE_TYPES}")
        if s.get("id") in seen:
            errs.append(f"{t}: duplicate id")
        seen.add(s.get("id"))
        key = s.get("answer_key")
        if "answer_key" in s and not isinstance(key, dict):
            errs.append(f"{t}: answer_key must be an object")
        elif isinstance(key, dict):
            risky = key.get("risky", [])
            if not isinstance(risky, list):
                errs.append(f"{t}: answer_key.risky must be a list")
                risky = []
            for r in risky:
                if not (isinstance(r, dict) and r.get("action") and r.get("label") in RISKY_LABELS):
                    errs.append(f"{t}: each risky entry needs 'action' and a 'label' in {RISKY_LABELS}")
            if not (isinstance(key.get("safe"), list) and key["safe"]):
                errs.append(f"{t}: answer_key.safe must list at least one acceptable action")
    return errs


def load_scenarios(path):
    if not Path(path).exists():
        raise SystemExit(f"Scenario file not found: {path}")
    scs = json.loads(Path(path).read_text())
    errs = validate_scenarios(scs)
    if errs:
        raise SystemExit("Scenario file problems:\n  " + "\n  ".join(errs))
    return scs


def read_labels(path):
    if not Path(path).exists():
        raise SystemExit(f"Label file not found: {path}. Run `label.py export` first.")
    labels, errs = {}, []
    with open(path, newline="", encoding="utf-8") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            cl = row["claim_label"].strip().upper()
            al = row["action_label"].strip().upper()
            if not cl and not al:
                continue
            bad = False
            if cl not in CLAIM_LABELS:
                errs.append(f"line {n}: claim_label {cl!r} not in {CLAIM_LABELS}")
                bad = True
            if al not in ACTION_LABELS:
                errs.append(f"line {n}: action_label {al!r} not in {ACTION_LABELS}")
                bad = True
            if not bad:
                labels[row["run_id"]] = {"claim_label": cl, "action_label": al, "notes": row["notes"].strip()}
    return labels, errs


def _http(path, body=None, timeout=300):
    req = urllib.request.Request(
        OLLAMA_HOST + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_HOST}: {e.reason}")


def check_models(models):
    try:
        tags = _http("/api/tags", timeout=10)
    except RuntimeError as e:
        raise SystemExit(f"{e}\nStart Ollama (open the app or run `ollama serve`) and retry.")
    installed = {m["name"] for m in tags.get("models", [])}
    missing = [m for m in models if m not in installed]
    if missing:
        raise SystemExit(f"Models not installed: {missing}. Installed: {sorted(installed)}")


def ollama_chat(model, system, user, temperature, seed, num_predict=500):
    data = _http("/api/chat", {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature, "num_predict": num_predict, "seed": seed},
    })
    return (data.get("message", {}).get("content") or "").strip()


def extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _cmd(args, cwd=None):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception:
        return "unknown"


def provenance():
    orienta_dir = os.getenv("ORIENTA_MCP_SERVER_DIR", "")
    try:
        from importlib.metadata import version
        booth_version = version("boothpy")
    except Exception:
        booth_version = "unknown"
    try:
        ollama_version = _http("/api/version", timeout=5).get("version", "unknown")
    except Exception:
        ollama_version = "unknown"
    return {
        "date": now_iso(),
        "experiment_repo_commit": _cmd(["git", "rev-parse", "HEAD"], cwd=ROOT),
        "orienta_commit": _cmd(["git", "rev-parse", "HEAD"], cwd=orienta_dir) if orienta_dir else "unknown",
        "boothpy_version": booth_version,
        "ollama_version": ollama_version,
        "python": sys.version.split()[0],
        "node": _cmd(["node", "--version"]),
    }