from dataclasses import asdict, replace
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from agent_regression.harness import Case, replay, run_agent
from agent_regression.statistics import (
    ReleasePlan,
    clopper_pearson,
    exact_discordance,
    holm_adjust,
    paired_bootstrap,
    release_demo,
    release_evaluate,
)


class StatisticalReleaseTests(unittest.TestCase):
    def fixture(self, count=100, **changes):
        cases = [Case(f"case-{i}", f"TASK: add {i} 1", "add", i, 1, tags=("addition",)) for i in range(count)]
        records = [{"case_id": case.case_id, "record": run_agent(case.prompt)} for case in cases]
        plan = ReleasePlan(
            "test-v1",
            replay(cases, records)["dataset_sha256"],
            "base@1",
            "candidate@2",
            bootstrap_samples=200,
            **changes,
        )
        return cases, records, plan

    def test_exact_discordance_matches_exhaustive_binary_outcomes(self):
        for n in range(9):
            counts = [sum(bits) for bits in itertools.product((0, 1), repeat=n)]
            for regressions in range(n + 1):
                result = exact_discordance(regressions, n - regressions)
                upper = sum(k >= regressions for k in counts) / len(counts)
                lower = sum(k <= regressions for k in counts) / len(counts)
                with self.subTest(n=n, regressions=regressions):
                    self.assertEqual(result["p_deterioration"], upper)
                    self.assertEqual(result["p_two_sided"], min(1, 2 * min(upper, lower)))
                    self.assertEqual(
                        int(result["exact_deterioration_numerator"]), sum(k >= regressions for k in counts)
                    )

    def test_extreme_exact_probability_retains_nonzero_integer_evidence(self):
        result = exact_discordance(1200, 0)
        self.assertEqual(result["exact_deterioration_numerator"], "1")
        self.assertEqual(result["denominator_power_two"], 1200)
        self.assertEqual(result["p_deterioration"], 0.0)  # Explicitly representable float underflow.
        self.assertEqual(exact_discordance(0, 0)["p_two_sided"], 1)

    def test_holm_adjustment_is_monotone_and_handles_ties(self):
        result = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertAlmostEqual(result["a"], 0.03)
        self.assertAlmostEqual(result["b"], 0.06)
        self.assertAlmostEqual(result["c"], 0.06)
        self.assertEqual(holm_adjust({"a": 0.01, "b": 0.01}), {"a": 0.02, "b": 0.02})

    def test_binomial_bounds_have_small_sample_exact_coverage(self):
        for n in range(1, 9):
            intervals = [clopper_pearson(k, n, 0.05) for k in range(n + 1)]
            for p in (0.05, 0.2, 0.5, 0.8, 0.95):
                coverage = sum(
                    math.comb(n, k) * p**k * (1 - p) ** (n - k)
                    for k, (lo, hi) in enumerate(intervals)
                    if lo - 1e-12 <= p <= hi + 1e-12
                )
                with self.subTest(n=n, p=p):
                    self.assertGreaterEqual(coverage + 1e-12, 0.9)
        self.assertAlmostEqual(clopper_pearson(0, 10, 0.025)[1], 1 - 0.025**0.1)

    def test_bootstrap_resamples_pairs_reproducibly(self):
        first = paired_bootstrap([-1, 1], samples=2000, alpha=0.05, seed=72)
        self.assertEqual(first, paired_bootstrap([-1, 1], samples=2000, alpha=0.05, seed=72))
        self.assertEqual((first["lower"], first["upper"]), (-1.0, 1.0))
        self.assertTrue(first["pointwise_not_simultaneous"])

    def test_zero_observed_changes_do_not_imply_zero_uncertainty(self):
        corpus, rows, plan = self.fixture(5, min_cases=30)
        report = release_evaluate(corpus, rows, rows, plan)
        self.assertFalse(report["gate_passed"])
        self.assertIn("insufficient_sample", {r["code"] for r in report["gate_reasons"]})
        self.assertEqual(report["slices"][0]["bootstrap_ci"]["lower"], 0)
        self.assertLess(report["slices"][0]["simultaneous_lower_delta_bound"], 0)
        self.assertTrue(report["slices"][0]["bootstrap_ci"]["degenerate_empirical_distribution"])

    def test_zero_tolerance_cannot_be_proven_from_finite_unchanged_sample(self):
        corpus, rows, plan = self.fixture(100, allowed_drop=0)
        report = release_evaluate(corpus, rows, rows, plan)
        self.assertFalse(report["gate_passed"])
        self.assertIn("noninferiority_unproven", {r["code"] for r in report["gate_reasons"]})

    def test_critical_failure_blocks_statistically_tolerable_change(self):
        corpus, baseline, plan = self.fixture(100, critical_case_ids=("case-1",), allowed_drop=0.20)
        candidate = json.loads(json.dumps(baseline))
        candidate[1]["record"] = run_agent(corpus[1].prompt, "wrong_arguments")
        report = release_evaluate(corpus, baseline, candidate, plan)
        self.assertTrue(report["slices"][0]["noninferiority_supported"])
        self.assertFalse(report["gate_passed"])
        self.assertEqual(report["critical_failed_case_ids"], ["case-1"])

    def test_large_deterioration_fails_exact_corrected_test(self):
        corpus, baseline, plan = self.fixture(100, allowed_drop=1, slice_tags=("addition",))
        candidate = [{"case_id": case.case_id, "record": run_agent(case.prompt, "wrong_arguments")} for case in corpus]
        report = release_evaluate(corpus, baseline, candidate, plan)
        self.assertFalse(report["gate_passed"])
        self.assertTrue(all(row["holm_adjusted_p_deterioration"] < 0.05 for row in report["slices"]))
        self.assertIn("significant_deterioration", {r["code"] for r in report["gate_reasons"]})

    def test_artifacts_bind_versions_inputs_dataset_and_configuration(self):
        corpus, rows, plan = self.fixture()
        first = release_evaluate(corpus, rows, rows, plan)
        self.assertTrue(first["gate_passed"])
        self.assertEqual(len(first["paired_cases"]), 100)
        second = release_evaluate(corpus, rows, rows, replace(plan, candidate_version="other@3"))
        self.assertNotEqual(first["artifact_sha256"], second["artifact_sha256"])
        self.assertEqual(first, release_evaluate(corpus, rows, rows, plan))
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            release_evaluate(corpus, rows, rows, replace(plan, dataset_sha256="0" * 64))

    def test_incomplete_replays_do_not_become_paired_statistical_samples(self):
        corpus, rows, plan = self.fixture()
        result = release_evaluate(corpus, rows, rows[:-1], plan)
        self.assertFalse(result["gate_passed"])
        self.assertEqual(result["slices"], [])
        self.assertEqual(result["gate_reasons"], [{"code": "incomplete_replay"}])

    def test_invalid_preregistration_and_unknown_slices_are_rejected(self):
        corpus, rows, plan = self.fixture()
        for change in (
            {"alpha": 0},
            {"alpha": float("nan")},
            {"bootstrap_samples": 199},
            {"allowed_drop": -1},
            {"slice_tags": ("x", "x")},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(plan, **change)
        with self.assertRaisesRegex(ValueError, "unknown slice"):
            release_evaluate(corpus, rows, rows, replace(plan, slice_tags=("missing",)))
        with self.assertRaisesRegex(ValueError, "unknown critical"):
            release_evaluate(corpus, rows, rows, replace(plan, critical_case_ids=("missing",)))

    def test_cli_writes_artifact_before_blocking_release(self):
        corpus, rows, plan = self.fixture(40, min_cases=100)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, content in [
                ("cases.jsonl", "".join(json.dumps(asdict(case)) + "\n" for case in corpus)),
                ("replay.jsonl", "".join(json.dumps(row) + "\n" for row in rows)),
                ("plan.json", json.dumps(asdict(plan))),
            ]:
                (folder / name).write_text(content)
            output = folder / "release.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent_regression",
                    "release",
                    "--cases",
                    str(folder / "cases.jsonl"),
                    "--baseline",
                    str(folder / "replay.jsonl"),
                    "--candidate",
                    str(folder / "replay.jsonl"),
                    "--plan",
                    str(folder / "plan.json"),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(output.read_text())["gate_passed"])

    def test_executed_synthetic_release_has_pass_and_critical_failure(self):
        report = release_demo()
        self.assertTrue(report["demonstration_passed"])
        self.assertEqual(len(report["positive"]["slices"]), 5)
        self.assertTrue(report["positive"]["gate_passed"])
        self.assertFalse(report["critical_regression"]["gate_passed"])


if __name__ == "__main__":
    unittest.main()
