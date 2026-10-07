# Independent review and verification

The audit examined oracle independence, output/trace validation, mutation denominators, metamorphic relations, replay completeness and CI exit behavior. Before edits, all 19 existing unit tests passed. The following defects were nevertheless reproduced.

| Finding and original proof | Fix and regression evidence |
| --- | --- |
| Adding `error: TOOL_DENIED` to an otherwise successful trace event still produced no validation failures. | Enforce exact success-event and top-level record schemas; contradictory/unknown fields fail `trace_schema`/`record_schema`. |
| `duplicate_call` emitted two trace events while a wrapped tool recorded only one actual invocation. | Execute the tool twice with distinct IDs; an independent mock wrapper asserts two invocations and the contract rejects the extra execution. |
| A malformed request with normal labels had a failing baseline, yet every no-op mutant reported 1/1 detected. | Only passing baselines and changed observations enter the eligible injection denominator; report attempted/excluded/unchanged separately. Such a case now reports zero eligible injections, null detection rates and a failing gate. |
| The executor accepted operand 10,001 despite the stated 10,000 bound. | Apply the exact executor bound, including fault-mutated arguments; the tool returns `INVALID_ARGUMENTS`. |
| Metamorphic results were only individually graded, with no source/variant relation. | Compare public behavior in pairs while ignoring arbitrary, consistently bound call IDs; explicitly exclude transformations that cross the request size limit. Add an untrusted instruction-injection variant. |
| Replay CLI could report partial coverage and still exit 0. | Full-corpus denominators, `complete`/`all_passed`, and nonzero failure exit codes after writing reviewable JSON. |

The new `compare` capability grades complete baseline/candidate replays against the same labels, then gates newly regressed cases. The committed negative candidate regresses `add-positive`; its comparison command returns 1 as intended. Known failures may persist under a regression comparison; ordinary replay evaluation remains the every-case gate.

## Commands actually run

From this standalone project directory after editable installation (the collection verification used its `.venv/bin/python`):

```bash
python -m unittest discover -s checks -v
python -m agent_regression demo --output baselines/demo.json
python -m agent_regression evaluate --output baselines/evaluation.json --export-traces baselines/baseline.jsonl
python -m agent_regression evaluate --replay baselines/baseline.jsonl --output baselines/replay-evaluation.json
python -m agent_regression compare --baseline baselines/baseline.jsonl --candidate baselines/candidate-regression.jsonl --output baselines/regression-comparison.json
python scripts/review_fault_probes.py --output baselines/review-fault-probes.json
```

Results: **30 tests pass; 21/21 baseline cases pass; 128/128 eligible named injections are detected; 48/48 metamorphic pairs pass; complete baseline replay passes 21/21.** The negative comparison returns **1** and identifies one new regression. Default evaluation and replay commands return **0**. Root Ruff `check --select E9,F` and `format --check` pass on this project.

## Test-quality evidence and limits

TestProof was absent: `npx --no-install testproof --version` failed because no local package was available. No executable was downloaded. The collection had no HEAD commit during the initial audit, so there was no ordinary git comparison base. No TestProof score is claimed.

Instead, `scripts/review_fault_probes.py` runs a green baseline, makes one explicitly selected change in an isolated source copy, and runs the unmodified tests. All **5/5 selected probes** were caught: permissive event schema, skipped duplicate execution, inflated injection denominator, partial-replay success, and metamorphic comparison that incorrectly includes run IDs. There were no probe timeouts. These five chosen probes do not represent broad mutation coverage, and they are separate from the eight fixture fault operators.

Remaining limits: arithmetic fixtures and hand-designed faults are narrow; expected labels are supplied independently and may themselves be wrong. Strict record consistency does not prove an imported collector really executed tools. No live agent, provider, external side effect, signed trace, production dataset or model quality benchmark was run. Source probes cover only their stated review behaviors. Raw synthetic examples remain local files; real sensitive traces require a separate retention/redaction policy.
