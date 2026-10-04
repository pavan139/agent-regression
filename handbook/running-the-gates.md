# Running and interpreting the gates

There are three different decisions: grading each replay against its labels, blocking newly regressed pairs, and applying the declared statistical release plan. Use the command matching the question rather than treating every green report as the same guarantee.

```bash
PYTHONPATH=src python -m unittest discover -s checks -v
python -m agent_regression evaluate --replay baselines/baseline.jsonl --output results/replay.json
python -m agent_regression release-demo --output results/release.json
python scripts/check_suite.py --require-lint --wheel
```

The recorded full suite has 44 passing tests on Python 3.12.14. The fixture evidence includes 21 baseline cases, 128 eligible named faults and 48 paired metamorphic variants. The separate release experiment has 240 pairs. [The machine-readable verification](../reports/verification.json) records the checked source and package-install results.

A replay with missing cases is incomplete even if every supplied row passes. A statistical bound that cannot establish the declared margin blocks release; zero observed regressions do not establish zero uncertainty. Critical-case failures override an otherwise acceptable aggregate. See [statistical gate evidence](statistical-gate-evidence.md) for the executed examples and limitations.
