# Change the grader with a failing trace

Start with a replay the current grader accepts incorrectly, or rejects despite meeting the stated contract. Add that record to `checks/` with an independently justified result. Keep the expected answer outside the fixture agent and mutation operator.

When changing mutation accounting, preserve all four distinctions: attempted fault, changed observable behavior, eligible baseline and detected failure. A baseline that already fails cannot prove the injected fault was detected. Metamorphic variants need both valid labels and an independently specified relation.

For statistical code, use hand-computed or exhaustively enumerated small cases. Check tail direction and bound coverage, then verify that missing cases and critical failures still block release. Do not alter alpha or slice definitions after inspecting the candidate run and describe it as preregistered.

```bash
python -m pip install -e . -r requirements-dev.txt
PYTHONPATH=src python -m unittest discover -s checks -v
python scripts/check_suite.py --require-lint --wheel
```

The optional selected fault-probe command is `python scripts/review_fault_probes.py --output results/source-probes.json`. It edits isolated copies, never the working source. Its result applies only to the named probes, not every possible fault.
