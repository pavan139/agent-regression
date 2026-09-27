# Paired release experiment

`statistics.py` grades replay pairs, computes exact discordance probabilities and returns a release decision with critical-case overrides. This note records the supplied synthetic comparison and its uncertainty calculations.

Implemented capabilities include integer-exact McNemar/binomial discordance tests, seeded paired bootstrap intervals, Holm-adjusted slice deterioration tests, simultaneous conservative Clopper–Pearson/Bonferroni lower bounds for net success change, sample minima, critical candidate-pass gates, dataset/version/input-bound artifacts, and a CLI that exports blocked decisions before exiting 1. Existing deterministic contract/mutation interfaces remain available.

## Reproduce the executed experiment

After `python -m pip install -e .`, from this repository:

```bash
python -m agent_regression release-demo --seed 17 --output baselines/release-experiment.json
python -m agent_regression release --cases suites/release-cases.jsonl --baseline baselines/release-baseline.jsonl --candidate baselines/release-candidate.jsonl --plan suites/release-plan.json --output baselines/release-report.json
python -m agent_regression release --cases suites/release-cases.jsonl --baseline baselines/release-baseline.jsonl --candidate baselines/release-critical-candidate.jsonl --plan suites/release-critical-plan.json --output baselines/release-critical-report.json
python -m unittest discover -s checks -v
```

The first two commands returned **0**. The third returned **1**, as intended for its injected critical failure. The suite passed **44 tests**, including all 30 pre-upgrade tests.

The seed-17 fixture draws 240 independent synthetic task pairs, with coupled baseline/candidate failure draws representing fictional error rates of 12% and 3%. It executes actual arithmetic-tool traces with injected argument faults. It does not call a model or provider.

| Executed result | Value |
| --- | ---: |
| Baseline success | 213 / 240 |
| Candidate success | 232 / 240 |
| Recoveries / regressions | 19 / 0 |
| Net success change | +0.0791667 |
| Pointwise 95% paired bootstrap CI, 1,000 replicates | [0.0458333, 0.1125000] |
| Exact two-sided discordance p-value | 2 / 2^19 = 0.0000038146973 |
| Simultaneous 95% global lower change bound | 0.0190736 |
| Declared allowed drop | 0.15 |
| Positive release / critical-fault release | pass / block |

The four operation slices have 51, 57, 68 and 64 cases. Their lower bounds are wider than the global bound. The configured 15-point margin is an illustrative preregistered tolerance, not a recommended production threshold. The injected critical candidate is a separately declared version and is blocked even though its aggregate change is tolerable under that margin.

## Independent probability checks

New tests enumerate every binary discordance assignment for trial counts zero through eight and compare exact tail probabilities for all 45 count configurations. Separate coverage checks enumerate binomial outcomes at eight sample sizes and five true probabilities, confirming the two-sided Clopper–Pearson coverage bound for those 40 configurations. Tests also cover Holm ties, probability underflow with preserved exact numerators, incomplete samples, insufficient sample size, zero-tolerance uncertainty, arbitrary paired bootstrap reproducibility, critical overrides and CLI failure artifacts.

No broad mutation score or repeated-peeking coverage claim is made. Existing source-fault probe artifacts describe the earlier selected review experiment; they are separate from these statistical probability tests.

## Limits

Inference requires appropriate independent case sampling within declared populations/slices, correct labels and fixed targets. The synthetic experiment demonstrates mechanics and known generation assumptions, not real-agent performance or production reliability. Clustering, adaptive case selection and repeated candidate inspection require another statistical design. Bootstrap CIs are descriptive; the release gate uses the finite-sample lower-bound construction. Holm and confidence-bound guarantees concern separately defined error events. More details, equations, complexity and failure behavior are in [paired-release-inference.md](paired-release-inference.md).
