# BOOTH vs. Orienta Experiment

Empirical evaluation and single-variable ablation study comparing **claim-level output verification with BOOTH** against **action-level governance with Orienta**, using Orienta through its Model Context Protocol (MCP) server interface.

> **Status:** Experimental research
> **Dataset:** 14 scenarios
> **Evaluation:** BOOTH, Orienta, and combined BOOTH + Orienta
> **LLM Judge:** Local Ollama models
> **Orienta Integration:** MCP over stdio

---

## Overview

Modern LLM agents can fail in two fundamentally different ways:

1. **They can make an unsupported or incorrect claim.**
2. **They can propose or attempt an action that violates a policy, authority boundary, or safety constraint.**

This repository investigates the distinction between these two failure modes.

**BOOTH** operates at the **claim/evidence layer**: it evaluates whether an agent's claim is supported by the available evidence.

**Orienta** operates at the **action/governance layer**: it reviews a proposed action in the context of the objective, surrounding circumstances, constraints, and applicable domain.

The experiment evaluates these systems independently and in combination rather than treating one as a replacement for the other.

```text
                    ┌──────────────────────┐
                    │    Agent Scenario    │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
        ┌─────────────────┐         ┌─────────────────┐
        │      BOOTH      │         │     Orienta     │
        │                 │         │                 │
        │ Claim           │         │ Proposed Action │
        │      +          │         │       +         │
        │ Evidence        │         │ Context         │
        └────────┬────────┘         └────────┬────────┘
                 │                           │
                 ▼                           ▼
          Evidence Verdict            Governance Verdict
                 │                           │
                 └─────────────┬─────────────┘
                               ▼
                     Combined Evaluation
```

---

## Research Collaboration

This work evaluates the interaction between claim-level verification and action-level governance in LLM-driven agent systems.

Special thanks to **Serena Wang** and the **Senux Research Lab** team for their collaboration and discussion around this evaluation.

### Upstream Project

- [Orienta](https://github.com/serenaw99/orienta) — action-level governance framework
- [BOOTH](https://github.com/Vedantgitbot/booth) — claim/evidence verification framework
- [Discussion & Issue Thread](https://github.com/SenuxTech/orienta/issues/4)

---

## Experimental Design

### 1. BOOTH

BOOTH evaluates an agent's claim against supplied evidence.

Conceptually:

```text
agent_claim + evidence
        │
        ▼
   BOOTH comparator
        │
        ▼
 evidence agreement score
        │
        ▼
   flagged / clear
```

The current experiment uses a local Ollama model as the evidence comparator. The comparator receives only:

- the agent claim
- the supplied evidence

It does **not** receive:

- the expected label
- the proposed action
- ground-truth annotations

This separation prevents the judge from directly seeing the experimental answer.

---

### 2. Orienta

Orienta evaluates the proposed action independently through its MCP server.

Conceptually:

```text
objective
context
proposed_action
domain
constraints
        │
        ▼
   Orienta MCP server
        │
        ▼
 PROCEED / MODIFY / ESCALATE / BLOCK
```

The BOOTH and Orienta evaluations are run as **parallel arms**, not as a pipeline.

---

### 3. Combined BOOTH + Orienta

The combined arm treats either system flagging a case as a safety/governance signal.

This allows the experiment to examine whether combining:

- claim-level verification, and
- action-level governance

provides broader coverage than either mechanism independently.

---

## Benchmark

The benchmark contains **14 independent scenarios** covering several classes of agent behavior:

- Policy constraints
- Authority and authorization limits
- Sensitive-data access
- Third-party mutations
- Unsupported claims
- Overstated claims
- Missing or insufficient evidence
- Edge-case policy boundaries

The dataset is intentionally small and should be treated as an **illustrative experimental benchmark**, not as a statistically representative measurement of system accuracy.

---

## Ablation Study

The repository also contains a single-variable ablation matrix designed to isolate the effect of individual inputs on Orienta's decisions.

The primary variables are:

| Variable      | Purpose                                                               |
| ------------- | --------------------------------------------------------------------- |
| `constraints` | Tests the effect of explicit policy or authorization constraints      |
| `agent_claim` | Tests how the agent's asserted state affects claim-level verification |
| `evidence`    | Tests how supporting or contradicting evidence affects BOOTH          |

Orienta decisions are evaluated across its governance outcomes:

```text
PROCEED
MODIFY
ESCALATE
BLOCK
```

The ablation results are used to investigate behavioral changes and identify potential root causes of non-deterministic decisions around policy boundaries.

---

## Repository Structure

```text
booth-orienta-experiment/
│
├── orienta_client.py
│   └── Thin MCP client for Orienta's review_objective tool
│
├── booth_adapter.py
│   └── BOOTH claim/evidence adapter using a local Ollama judge
│
├── run_experiment.py
│   └── Benchmark runner and BOOTH vs. Orienta comparison logic
│
├── sample_cases.json
│   └── Example test-case definitions
│
├── baseline_v1_cases.json
│   └── Frozen 14-scenario evaluation dataset
│
├── baseline_v1_results.json
│   └── Raw output from the v1 MCP evaluation
│
├── baseline_v2_judge_llama31_8b.json
│   └── Llama 3.1 8B judge outputs
│
└── results_judge_llama31_8b.json
    └── Final ablation/evaluation results
```

---

## Quickstart

### Prerequisites

- Python 3.10+
- Node.js
- Orienta's MCP server
- Ollama
- At least one locally installed Ollama model

For example:

```bash
ollama list
```

If multiple models are installed, select the model used by the experiment:

```bash
export OLLAMA_MODEL=llama3.1:8b
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/Vedantgitbot/booth-orienta-experiment.git
cd booth-orienta-experiment
```

Install the Python dependencies:

```bash
pip install boothpy mcp httpx
```

Ensure Ollama is running and that your selected model is available locally.

---

## Orienta MCP Configuration

The BOOTH experiment communicates with Orienta through its MCP server rather than importing or modifying Orienta's source code.

Set the Orienta MCP server location:

```bash
export ORIENTA_MCP_SERVER_DIR=../mcp-server
```

The exact server command depends on the Orienta checkout.

Configure it with:

```bash
export ORIENTA_MCP_COMMAND=node
export ORIENTA_MCP_ARGS="server.js"
```

Verify the corresponding command against the `mcp-server/package.json` in your local Orienta checkout before running the experiment.

The integration is intentionally kept separate:

```text
BOOTH experiment
      │
      │ MCP / stdio
      ▼
Orienta MCP server
      │
      ▼
Orienta
```

No Orienta source code is imported, forked, or modified by the client.

---

## Running the Experiment

The runner accepts an input case file and an output path:

```bash
python run_experiment.py sample_cases.json results.json
```

For the frozen benchmark:

```bash
python run_experiment.py baseline_v1_cases.json baseline_v1_results.json
```

The runner reports:

- Agreement buckets
- BOOTH correctness
- Orienta correctness
- Combined correctness
- Per-case outcomes

Full structured results are written to the specified JSON output file.

---

## Evaluation Outputs

Each case records the results of both evaluation arms.

### BOOTH

```json
{
  "flagged": true,
  "inconclusive": false,
  "status": "BLOCKED",
  "score": 0.42
}
```

### Orienta

```json
{
  "decision": "BLOCK",
  "flagged": true,
  "reason_codes": [],
  "reasoning": "...",
  "orientation_evidence": []
}
```

### Agreement Buckets

The experiment categorizes each case into one of the following buckets:

| Bucket                | Meaning                                      |
| --------------------- | -------------------------------------------- |
| `BOTH_FLAGGED`        | BOOTH and Orienta both flagged the case      |
| `BOTH_CLEAR`          | Neither system flagged the case              |
| `BOOTH_ONLY`          | BOOTH flagged; Orienta did not               |
| `ORIENTA_ONLY`        | Orienta flagged; BOOTH did not               |
| `BOOTH_INCONCLUSIVE`  | BOOTH could not produce a conclusive verdict |
| `ORIENTA_CALL_FAILED` | The Orienta MCP call failed                  |

---

## Ground-Truth Evaluation

The experiment distinguishes between **agreement** and **correctness**.

Two systems agreeing does not necessarily mean they are correct.

Where ground-truth labels are available, the runner separately evaluates:

```text
BOOTH correctness
        │
        ├── vs. expected BOOTH flag
        │
Orienta correctness
        │
        ├── vs. expected action label
        │
Combined correctness
        │
        └── vs. expected action label
```

This distinction is important when interpreting results.

---

## Local LLM Judge

BOOTH's evidence comparator uses a local Ollama model.

The model receives a structured prompt containing:

```text
EVIDENCE:
...

CLAIM:
...
```

and returns a support score between `0.0` and `1.0`.

The current fixed evidence threshold is:

```text
0.7
```

The threshold is fixed **before evaluating the benchmark** and should not be tuned against the evaluation results.

The model name and comparator version are recorded in the experiment output to improve reproducibility.

### Important limitation

Small local models can introduce judge noise.

Unexpected BOOTH scores may therefore reflect limitations of the local comparator rather than a substantive property of BOOTH itself.

For this reason, reported results should always include the exact judge model used.

---

## Reproducibility

For reproducible experiments, record:

- Git commit of this repository
- Orienta revision/commit
- BOOTH revision/commit
- Ollama version
- Ollama model and model version/tag
- Python version
- Node.js version
- Benchmark dataset
- Evidence threshold
- Experiment output JSON

Example:

```bash
python --version
node --version
ollama --version
ollama list
git rev-parse HEAD
```

---

## Limitations

This experiment has several important limitations.

### Small benchmark

The benchmark contains 14 scenarios and is intended for exploratory evaluation rather than statistical claims about general performance.

### Hand-written claims

There is no live autonomous agent in the current experiment. `agent_claim` values are manually constructed test inputs.

Therefore, the results should not be interpreted as an evaluation of an end-to-end autonomous agent.

### Local judge variability

BOOTH's comparator is an LLM-based judge running locally through Ollama. Different models may produce different evidence-support scores.

### Parallel evaluation

BOOTH and Orienta are evaluated independently. The experiment does not claim that either system's output would influence the other during an actual agent execution.

### No production safety guarantee

The benchmark evaluates experimental behavior under predefined scenarios. Passing these cases does not establish that either system is safe for production deployment.

---

## Research Interpretation

The central research question is not simply:

> Which system is better?

Instead, the experiment investigates whether **claim-level verification and action-level governance detect different classes of failures**.

A useful conceptual distinction is:

```text
"What the agent says"
        │
        ▼
     BOOTH
        │
   Claim ↔ Evidence


"What the agent wants to do"
        │
        ▼
    Orienta
        │
 Action ↔ Context / Constraints
```

The combined system therefore provides two different verification surfaces rather than two implementations of the same check.

---

## Attribution

This repository contains experimental evaluation code integrating BOOTH with Orienta.

Please attribute the original projects and governance concepts appropriately:

- **BOOTH:** [Vedantgitbot/booth](https://github.com/Vedantgitbot/booth)
- **Orienta:** [serenaw99/orienta](https://github.com/serenaw99/orienta)
- **Senux Research Lab:** collaboration and upstream Orienta work

For discussions regarding the Orienta integration, see:

[SenuxTech/orienta#4](https://github.com/SenuxTech/orienta/issues/4)

---

## License

This evaluation repository is released under the **MIT License**.

See the repository's `LICENSE` file for the full license text.

---

## Citation

If you use this benchmark or evaluation framework in research, please cite the repository and the underlying BOOTH and Orienta projects.

```text
BOOTH vs. Orienta Experiment
Empirical evaluation of claim-level verification
and action-level governance in LLM agent systems.
```

---

## Disclaimer

This repository is an experimental research artifact. Results from the included benchmark should not be interpreted as a comprehensive safety evaluation, production readiness assessment, or statistically significant comparison of BOOTH and Orienta.
