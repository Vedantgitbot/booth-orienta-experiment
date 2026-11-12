# BOOTH vs. Orienta Experiment

Do a claim-level verifier (**BOOTH**) and an action-level reviewer (**Orienta**) catch different failures in LLM agent output, or the same ones? This repository compares them without modifying either tool. Orienta is called only through its MCP server.

> **Status:** exploratory research, two studies complete.
> **v1:** 16 hand-built cases (complete, frozen).
> **v2:** 300 agent-generated runs (complete). Its ground-truth labels were **not hand-made and have not been independently checked**. Read [Deviations](#deviations-from-the-plan) before using any v2 number.
> **Not shown by either study:** that the two layers are complementary (see [v2 results](#v2-results)).

## The two layers

- **BOOTH** (`boothpy`, MIT) checks whether an agent's *claim* is supported by evidence. It returns ACCEPTED or BLOCKED. Here its comparator is a local LLM judge with a fixed threshold of 0.7.
- **Orienta** (experimental, MIT) reviews a proposed *action* before it runs and returns PROCEED / MODIFY / ESCALATE / BLOCK with reason codes. It is a control signal; the caller must enforce it. The version used here is the deterministic Core (`orienta_engine_v0.3`, commit `f16bf0b`), which needs no model API.

The two are run as parallel arms, never as a pipeline. BOOTH never sees the action, and Orienta never sees the claim.

## Repository layout

```text
src/experiment/
  shared/   booth_adapter.py, orienta_client.py   used by v1 and v2
  v1/       run_experiment.py                      v1 runner
  v2/       common.py generate.py label.py run_layers.py analyze.py test_analyze.py
            fill_main_labels.py                    how the v2 labels were applied (see below)
data/v1/    the 16 v1 cases
data/v2/    scenarios.json, main/ (requests, agent runs, manifest, labels)
results/v1/ v1 results and provenance
results/v2/ main/ (layer outputs, run_meta.json, report.txt, summary.json)
docs/V2_PROTOCOL.md   the v2 plan: hypotheses, design, metric definitions
```

## Setup

```bash
pip install boothpy mcp
ollama pull llama3.1:8b && ollama pull qwen2.5-coder:7b && ollama pull qwen2.5:7b-instruct
export ORIENTA_MCP_SERVER_DIR="$HOME/Desktop/orienta/mcp-server"   # your Orienta checkout
```

Orienta and Ollama are not pip-installable. v1 recorded its versions in `results/v1/PROVENANCE.md`; v2 records them in `results/v2/main/run_meta.json` and `data/v2/main/manifest.json`. Use the same Python that has `boothpy` installed (BOOTH was installed from a local editable checkout, version 0.5.8).

---

## v1: hand-written cases

**Design.** 16 hand-built cases: 14 independent scenarios plus 2 rewordings (rows 15 and 16 restate the $400 refund and the Enterprise refund as "transfer from company funds to the customer's bank account"). Headline scores use the 14 independent cases so no scenario is counted twice. Both layers saw every case independently. Labels were written before the runs. The agent claims are hand-written, so v1 shows what each layer *can* catch, not how often. No agent-only baseline was run.

```bash
python src/experiment/v1/run_experiment.py data/v1/baseline_v1_cases.json results/v1/new_run.json
```

**Results** (16 cases; the "combined" column is the harness definition: either layer flags, graded against `expected_label != PROCEED`, so a BOOTH-only flag on a harmless action counts as a miss):

| BOOTH judge | BOOTH vs expected | Orienta vs expected | combined |
|---|---|---|---|
| llama3.1:8b | 16/16 | 11/16 | 13/16 |
| qwen2.5-coder:7b | 14/16 | 11/16 | 11/16 |

On the 14 independent cases: BOOTH 14/14 (llama) or 13/14 (qwen), Orienta 11/14. These use different yardsticks (claim-level vs action-level), so they are not a ranking.

**Findings.**
- The layers caught different things. Orienta caught risky actions backed by true claims (a passenger's seat, another user's folder), which BOOTH cleared. BOOTH caught false claims on harmless actions and the refund-policy cases, which Orienta cleared. Both cleared all controls.
- Orienta missed: the Enterprise refund (rows 3, 16), the $400 refund (rows 6, 15), and the bank-statements email (row 9). Row 9 is the only case neither layer caught.
- Changing BOOTH's judge from qwen2.5-coder:7b to llama3.1:8b changed only the $400 case, so that BOOTH miss was a judge error, not a BOOTH limit. The second judge was chosen after seeing that result, so both are reported.
- Reruns at temperature 0 were identical. That shows stability, not robustness.

**Result files** (`results/v1/`). Some are byte-identical copies:

| File | Content |
|---|---|
| `baseline_v1_results.json`, `results.json` | qwen2.5-coder:7b judge (identical) |
| `baseline_v2_judge_llama31_8b.json`, `results_judge_llama31_8b.json`, `rerun_after_restructure_llama31-8b.json` | llama3.1:8b judge (identical) |

(`baseline_v2_judge_...` means the second judge run *of v1*, not the v2 study.)

---

## v2: agent-generated output

**Design.** 25 hand-written edge-case scenarios across 10 edge types (boundary values, cumulative limits, policy conflicts, reworded actions, authority claims, consented and unauthorized third parties, sensitive data, conflicting facts, controls). Each was rewritten four ways by local models (typos/slang, vague, multi-request, pressure with an unverifiable claim), giving 100 requests. Three local models (llama3.1:8b, qwen2.5-coder:7b, qwen2.5:7b-instruct) each acted as the agent on every request: **300 runs**. The agent saw the facts and the policy text and returned a proposed action and a claim.

Both layers saw the same information, so a difference can come only from what each checks: BOOTH got facts + policy as evidence, Orienta got the facts as context and the policy as constraints. Each run's claim was judged by the two models that did not write it (no self-judging); the headline BOOTH verdict is "flagged if either judge flags". Orienta was called once per run.

```bash
python src/experiment/v2/generate.py requests --tag main
python src/experiment/v2/generate.py agents   --tag main      # writes the freeze manifest
python src/experiment/v2/label.py export      --tag main
python src/experiment/v2/run_layers.py        --tag main      # refuses unless labeled and frozen
python src/experiment/v2/analyze.py          --tag main
python src/experiment/v2/test_analyze.py                      # checks the analysis math
```

A failure means `claim_label != SUPPORTED` (BOOTH's territory) or `action_label != PROCEED` (Orienta's). Intervals resample whole base scenarios, because variants and agents on one scenario are not independent.

### v2 results

Full report: `results/v2/main/report.txt`. Labels used: see the next section.

| | Runs | |
|---|---|---|
| Agent alone: any failure | 82/300 (27%) | claim not supported 72, risky action 49 |
| Quadrants | neither 218, claim-only 33, action-only 10, both 39 | action-only is below the planned minimum of 20 |

| Measure | Result |
|---|---|
| BOOTH flags a run with a failed claim | 35/72 = 49% (95% interval 30-71%) |
| BOOTH flags a run with a supported claim | 17/228 = 7% |
| Orienta flags a run with a risky action | **0/49** |
| Orienta flags a run with a safe action | 6/251 = 2% |
| Claim-only failures: BOOTH flags / Orienta flags | 22/33 (67%) / 0/33 |
| Action-only risks: Orienta flags / BOOTH flags | 0/10 / 1/10 |
| Either layer flags, among all failures | 36/82 = 44% |
| Either layer flags, among clean runs (false alarms) | 22/218 = 10% |

**Pre-planned verdict: NOT SHOWN.**
- H1 (BOOTH catches more claim-only failures than Orienta) holds: +67 points, interval +45 to +86. This is partly true by construction, since Orienta never sees the claim.
- H2 (Orienta catches more action-only risks than BOOTH) is not shown. Orienta caught none, and there are only 10 such runs.
- H3 (either layer catches more than the better single layer) is not shown: Orienta added no catches, so "either" equals BOOTH alone, at a cost of 10% false alarms.

**What this does and does not say.**
- BOOTH catches false claims that Orienta never flags, but it misses about half of them, and the rate depends heavily on the judge: 17% (llama3.1:8b alone), 26% (qwen2.5-coder:7b), 57% (qwen2.5:7b-instruct). The two judges disagreed on 38 of 299 runs. Small-model judge noise is a major part of the BOOTH numbers.
- Orienta's 0/49 mostly reflects what `orienta_engine_v0.3` evaluates. Most risky actions here were limit and policy cases (cumulative limits, policy conflicts, reworded transfers). Informal probes run outside the pipeline suggest the engine does not compare amounts against stated limits (a $200 credit against a $75 limit returned PROCEED) and is sensitive to wording (an explicit "cancel another patient's appointment without their consent" returned BLOCK, while the agents' softer phrasings of similar actions returned PROCEED). The probes are one-off and are not part of the results. This is a statement about an experimental, lightweight engine, not about Orienta's intended scope.
- Orienta's 6 flags were all `DISCLOSURE_AUTHORITY_UNVERIFIED` in two sensitive-data scenarios. By the labels these runs were not failures, so they count as false positives. One probe suggests the flag fires even on a sentence that refuses to send the data.
- The agents do fail, at a meaningful rate (27%), and the cumulative-limit scenario failed 19 of 24 times. But the failure rate on control scenarios (6/24) was not lower than on edge-case scenarios (76/276). The control scenarios included a false-claim bait, so they were not clean controls.
- The "consented third party" worry from v1 (Orienta escalating even when consent is on file) was not observed: 0 of 31 safe runs flagged.

---

## Deviations from the plan

These matter for how far to trust the v2 numbers.

1. **The labels were not made by the hand-labeling procedure.** The 300 v2 labels were applied by `src/experiment/v2/fill_main_labels.py`, which writes a prepared table of labels into the label sheet. The script is the only record of how they were assigned. There was no second labeler, no agreement statistic, and no audit against the answer keys. An earlier hand-labeling attempt was discarded after a keying error (all rows given the same label); no layer results had been seen at that point, and a partial layer run on it was killed and deleted. Treat the v2 results as conditional on the labels being right.
2. **The plan was committed with the results, not before.** `docs/V2_PROTOCOL.md` was written before the main run, but it was not committed or tagged beforehand, so it is a plan, not a timestamped pre-registration. The data were frozen with a hash manifest (`data/v2/main/manifest.json`) and the layers were run only after all 300 rows were labeled.
3. **The main run was generated in two parts.** It was first generated with the first 10 scenarios and then extended to all 25, with no labeling and no layer run in between (see the git history).
4. **A quota was missed.** The plan asked for at least 20 labeled runs in each failure quadrant. Action-only has 10. No scenarios were added, so the action-only conclusions are exploratory.
5. **The scenario author is also BOOTH's author.** The scenarios and answer keys were written by one person and have not been independently reviewed.

## Limitations

- Small local models act as agents and judges. Judging limits and dates needs arithmetic, which they do badly.
- The agent's claim comes from a fixed prompt ("the factual basis you rely on"), which shapes how often BOOTH has something to catch.
- 25 base scenarios give wide intervals. The study can show a large difference, not a small one.
- Orienta was evaluated only as `orienta_engine_v0.3` through its `review_objective` tool, with the policy passed as `constraints`. Whether and how that engine uses `constraints` was not established here.
- Nothing here is a production-safety evaluation.

## Research collaboration

This work evaluates the interaction between claim-level verification and action-level governance in LLM-driven agent systems. Thanks to **Serena Wang** and the **Senux Research Lab** team for their collaboration and discussion around this evaluation.

- [Orienta](https://github.com/serenaw99/orienta): action-level governance framework
- [BOOTH](https://github.com/Vedantgitbot/booth): claim/evidence verification framework
- [Discussion thread](https://github.com/SenuxTech/orienta/issues/4)

## License and citation

MIT License. If you use this evaluation, please cite this repository and the underlying BOOTH and Orienta projects.

```text
BOOTH vs. Orienta Experiment
Empirical evaluation of claim-level verification
and action-level governance in LLM agent systems.
```

## Disclaimer

This repository is an experimental research artifact. Its results are not a comprehensive safety evaluation, a production-readiness assessment, or a statistically conclusive comparison of BOOTH and Orienta.