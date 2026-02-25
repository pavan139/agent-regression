"""Preregistered paired release inference over independently graded replay cases."""

from __future__ import annotations
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import random
from typing import Any
from .harness import Case, replay

IMPLEMENTATION = "paired-release-v1"


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ReleasePlan:
    experiment_id: str
    dataset_sha256: str
    baseline_version: str
    candidate_version: str
    slice_tags: tuple[str, ...] = ()
    critical_case_ids: tuple[str, ...] = ()
    alpha: float = 0.05
    allowed_drop: float = 0.10
    min_cases: int = 30
    min_slice_cases: int = 20
    bootstrap_samples: int = 2000
    seed: int = 17

    def __post_init__(self):
        for value in (self.experiment_id, self.baseline_version, self.candidate_version):
            if type(value) is not str or not 1 <= len(value) <= 128:
                raise ValueError("Experiment and system versions must be explicit bounded strings")
        if (
            type(self.dataset_sha256) is not str
            or len(self.dataset_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.dataset_sha256)
        ):
            raise ValueError("Plan requires the exact case dataset SHA-256")
        if type(self.alpha) not in (int, float) or not 1e-6 <= self.alpha <= 0.2:
            raise ValueError("alpha must be in [0.000001, 0.2]")
        if type(self.allowed_drop) not in (int, float) or not 0 <= self.allowed_drop <= 1:
            raise ValueError("allowed_drop must be in [0,1]")
        for values, limit in ((self.slice_tags, 16), (self.critical_case_ids, 10000)):
            if (
                not isinstance(values, tuple)
                or len(values) > limit
                or any(type(v) is not str or not 1 <= len(v) <= 128 for v in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError("Slices and critical IDs must be unique bounded tuples")
        if any(type(n) is not int or not 1 <= n <= 10000 for n in (self.min_cases, self.min_slice_cases)):
            raise ValueError("Minimum sample sizes must be in [1,10000]")
        if (
            type(self.bootstrap_samples) is not int
            or not 200 <= self.bootstrap_samples <= 10000
            or type(self.seed) is not int
        ):
            raise ValueError("Use 200 to 10000 bootstrap replicates and an integer seed")

    @classmethod
    def from_dict(cls, row):
        if not isinstance(row, dict):
            raise ValueError("Release plan must be an object")
        values = dict(row)
        for key in ("slice_tags", "critical_case_ids"):
            if key in values:
                if not isinstance(values[key], (list, tuple)):
                    raise ValueError("Slice and critical specifications must be arrays")
                values[key] = tuple(values[key])
        try:
            return cls(**values)
        except TypeError as exc:
            raise ValueError("Unknown or missing release plan fields") from exc


def exact_discordance(regressions: int, recoveries: int) -> dict:
    """Exact conditional McNemar: B | B+C ~ Binomial(B+C, 1/2).

    Keep integer numerators to distinguish very small probabilities from float
    underflow. No chi-squared approximation or continuity correction is used.
    """
    if any(type(x) is not int or x < 0 for x in (regressions, recoveries)) or regressions + recoveries > 10000:
        raise ValueError("Discordant counts must be nonnegative and total at most 10000")
    n = regressions + recoveries
    denominator = 1 << n

    def lower_tail(k):
        coefficient = total = 1
        for j in range(1, k + 1):
            coefficient = coefficient * (n - j + 1) // j
            total += coefficient
        return total

    greater_numerator = lower_tail(n - regressions)
    two_numerator = min(denominator, 2 * lower_tail(min(regressions, recoveries)))
    return {
        "discordant_pairs": n,
        "regressions": regressions,
        "recoveries": recoveries,
        "p_deterioration": greater_numerator / denominator,
        "p_two_sided": two_numerator / denominator,
        "exact_deterioration_numerator": str(greater_numerator),
        "exact_two_sided_numerator": str(two_numerator),
        "denominator_power_two": n,
    }


def holm_adjust(values: dict[str, float]) -> dict[str, float]:
    if not values or any(
        type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in values.values()
    ):
        raise ValueError("Holm requires nonempty valid p-values")
    adjusted, running = {}, 0.0
    for index, (name, p) in enumerate(sorted(values.items(), key=lambda item: (item[1], item[0]))):
        running = max(running, min(1.0, (len(values) - index) * p))
        adjusted[name] = running
    return adjusted


def _binomial_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n or p == 0:
        return 1.0
    if p == 1:
        return 0.0
    log_term = n * math.log1p(-p)
    log_total = log_term
    ratio = math.log(p) - math.log1p(-p)
    for j in range(1, k + 1):
        log_term += math.log(n - j + 1) - math.log(j) + ratio
        hi, lo = max(log_total, log_term), min(log_total, log_term)
        log_total = hi + math.log1p(math.exp(lo - hi))
    return min(1.0, math.exp(log_total))


def clopper_pearson(k: int, n: int, tail_alpha: float) -> tuple[float, float]:
    """Two one-sided exact binomial bounds, numerically inverted by bisection."""
    if type(n) is not int or type(k) is not int or not 0 <= k <= n or n < 1 or not 0 < tail_alpha < 0.5:
        raise ValueError("Invalid binomial confidence-bound inputs")
    if k == 0:
        lower = 0.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(55):
            middle = (lo + hi) / 2
            if _binomial_cdf(k - 1, n, middle) > 1 - tail_alpha:
                lo = middle
            else:
                hi = middle
        lower = lo
    if k == n:
        upper = 1.0
    elif k == 0:
        upper = -math.expm1(math.log(tail_alpha) / n)
    else:
        lo, hi = 0.0, 1.0
        for _ in range(55):
            middle = (lo + hi) / 2
            if _binomial_cdf(k, n, middle) > tail_alpha:
                lo = middle
            else:
                hi = middle
        upper = hi
    return lower, upper


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    left = int(position)
    return ordered[left] + (ordered[min(left + 1, len(ordered) - 1)] - ordered[left]) * (position - left)


def paired_bootstrap(deltas: list[int], *, samples: int, alpha: float, seed: int) -> dict:
    if not deltas or any(type(x) is not int or x not in (-1, 0, 1) for x in deltas):
        raise ValueError("Bootstrap requires paired binary-outcome differences")
    if type(samples) is not int or not 200 <= samples <= 10000 or not 0 < alpha < 1 or type(seed) is not int:
        raise ValueError("Invalid bootstrap configuration")
    rng = random.Random(seed)
    n = len(deltas)
    estimates = [sum(deltas[rng.randrange(n)] for _ in range(n)) / n for _ in range(samples)]
    return {
        "method": "paired_percentile_bootstrap",
        "replicates": samples,
        "seed": seed,
        "confidence_level": 1 - alpha,
        "lower": _quantile(estimates, alpha / 2),
        "upper": _quantile(estimates, 1 - alpha / 2),
        "pointwise_not_simultaneous": True,
        "degenerate_empirical_distribution": len(set(deltas)) == 1,
    }


def release_evaluate(corpus: list[Case], baseline: list[dict], candidate: list[dict], plan: ReleasePlan) -> dict:
    before, after = replay(corpus, baseline), replay(corpus, candidate)
    if before["dataset_sha256"] != plan.dataset_sha256:
        raise ValueError("Release plan dataset fingerprint does not match the independently labeled corpus")
    ids = {case.case_id for case in corpus}
    if not set(plan.critical_case_ids) <= ids:
        raise ValueError("Plan includes unknown critical case IDs")
    if not set(plan.slice_tags) <= {tag for case in corpus for tag in case.tags}:
        raise ValueError("Plan includes unknown slice tags")
    binding = {
        "implementation": IMPLEMENTATION,
        "plan": asdict(plan),
        "baseline_sha256": fingerprint(baseline),
        "candidate_sha256": fingerprint(candidate),
    }
    artifact = {
        "schema_version": 1,
        "experiment_binding": binding,
        "artifact_sha256": fingerprint(binding),
        "baseline": {"passed": before["passed"], "missing": before["missing_case_ids"]},
        "candidate": {"passed": after["passed"], "missing": after["missing_case_ids"]},
        "gate_passed": False,
        "gate_reasons": [],
        "slices": [],
        "inference_scope": "Fixed preregistered comparison; no repeated-peeking or sequential validity claim.",
    }
    if not before["complete"] or not after["complete"]:
        artifact["gate_reasons"].append({"code": "incomplete_replay"})
        return artifact
    old = {row["case_id"]: int(row["passed"]) for row in before["outcomes"]}
    new = {row["case_id"]: int(row["passed"]) for row in after["outcomes"]}
    artifact["paired_cases"] = [
        {
            "case_id": case.case_id,
            "baseline_passed": bool(old[case.case_id]),
            "candidate_passed": bool(new[case.case_id]),
            "delta": new[case.case_id] - old[case.case_id],
            "tags": list(case.tags),
            "critical": case.case_id in plan.critical_case_ids,
        }
        for case in corpus
    ]
    critical_failed = sorted(case_id for case_id in plan.critical_case_ids if not new[case_id])
    artifact["critical_failed_case_ids"] = critical_failed
    if critical_failed:
        artifact["gate_reasons"].append({"code": "critical_failure", "case_ids": critical_failed})
    slices = [
        ("global", corpus),
        *[(f"tag:{tag}", [case for case in corpus if tag in case.tags]) for tag in plan.slice_tags],
    ]
    if plan.bootstrap_samples * sum(len(rows) for _, rows in slices) > 20_000_000:
        raise ValueError("Requested bootstrap work exceeds 20000000 paired resamples; reduce replicates or slices")
    family_size = len(slices)
    for name, selected in slices:
        deltas = [new[case.case_id] - old[case.case_id] for case in selected]
        n = len(deltas)
        regressions, recoveries = deltas.count(-1), deltas.count(1)
        exact = exact_discordance(regressions, recoveries)
        # Union bound across two binomial marginals and all declared slices.
        tail = plan.alpha / (2 * family_size)
        _, upper_regression = clopper_pearson(regressions, n, tail)
        lower_recovery, _ = clopper_pearson(recoveries, n, tail)
        lower_delta = lower_recovery - upper_regression
        slice_seed = int(hashlib.sha256(f"{plan.seed}:{name}".encode()).hexdigest()[:16], 16)
        row = {
            "name": name,
            "cases": n,
            "baseline_passed": sum(old[c.case_id] for c in selected),
            "candidate_passed": sum(new[c.case_id] for c in selected),
            "delta": sum(deltas) / n,
            "discordance_test": exact,
            "bootstrap_ci": paired_bootstrap(deltas, samples=plan.bootstrap_samples, alpha=plan.alpha, seed=slice_seed),
            "simultaneous_lower_delta_bound": lower_delta,
            "simultaneous_bound_method": "Clopper-Pearson marginal bounds plus Bonferroni union bound",
            "family_confidence_level": 1 - plan.alpha,
            "bound_tail_alpha": tail,
            "noninferiority_supported": lower_delta >= -plan.allowed_drop,
        }
        minimum = plan.min_cases if name == "global" else plan.min_slice_cases
        row["minimum_cases"] = minimum
        row["sufficient_sample_size"] = n >= minimum
        if n < minimum:
            artifact["gate_reasons"].append(
                {"code": "insufficient_sample", "slice": name, "cases": n, "minimum": minimum}
            )
        if not row["noninferiority_supported"]:
            artifact["gate_reasons"].append({"code": "noninferiority_unproven", "slice": name})
        artifact["slices"].append(row)
    adjusted = holm_adjust({row["name"]: row["discordance_test"]["p_deterioration"] for row in artifact["slices"]})
    for row in artifact["slices"]:
        row["holm_adjusted_p_deterioration"] = adjusted[row["name"]]
        if adjusted[row["name"]] <= plan.alpha:
            artifact["gate_reasons"].append({"code": "significant_deterioration", "slice": row["name"]})
    artifact["gate_passed"] = not artifact["gate_reasons"]
    artifact["limitations"] = [
        "Case pairs must be independent sampling units; clustered/repeated trials need cluster inference.",
        "Percentile bootstrap intervals are descriptive and can be degenerate; release gates use simultaneous finite-sample bounds.",
        "Holm controls the declared deterioration-test family; the bound family uses a separate conservative Bonferroni construction.",
        "Labels and system-version declarations are supplied by the experiment owner, not cryptographically attested.",
        "Do not repeatedly inspect this fixed-sample test and claim unchanged error guarantees.",
    ]
    return artifact


def synthetic_release_fixture(seed: int = 17):
    """Seeded independent synthetic case pairs; this is not real-model evidence."""
    from .harness import run_agent

    corpus, baseline, candidate = [], [], []
    rng = random.Random(seed)
    operations = ("add", "subtract", "multiply", "divide")
    for index in range(240):
        op, left, right = rng.choice(operations), rng.randint(-100, 100), rng.randint(1, 9)
        shared_failure_draw = rng.random()
        case = Case(f"release-{index:03}", f"TASK: {op} {left} {right}", op, left, right, tags=(op,))
        corpus.append(case)
        baseline.append(
            {
                "case_id": case.case_id,
                "record": run_agent(case.prompt, "wrong_arguments" if shared_failure_draw < 0.12 else None),
            }
        )
        candidate.append(
            {
                "case_id": case.case_id,
                "record": run_agent(case.prompt, "wrong_arguments" if shared_failure_draw < 0.03 else None),
            }
        )
    dataset = replay(corpus, baseline)["dataset_sha256"]
    plan = ReleasePlan(
        "synthetic-release-240-iid-v1",
        dataset,
        "fixture-baseline-v1",
        "fixture-candidate-v2",
        slice_tags=operations,
        critical_case_ids=tuple(f"release-{i:03}" for i in (0, 1, 2, 3)),
        allowed_drop=0.15,
        min_cases=100,
        min_slice_cases=40,
        bootstrap_samples=1000,
        seed=seed,
    )
    return corpus, baseline, candidate, plan


def release_demo(seed: int = 17) -> dict:
    """A seeded synthetic release experiment, not a real model comparison."""
    from .harness import run_agent

    corpus, baseline, candidate, plan = synthetic_release_fixture(seed)
    positive = release_evaluate(corpus, baseline, candidate, plan)
    bad = json.loads(json.dumps(candidate))
    bad[1]["record"] = run_agent(corpus[1].prompt, "wrong_arguments")
    critical = release_evaluate(
        corpus, baseline, bad, replace(plan, candidate_version="fixture-candidate-v2-criticalfault")
    )
    return {
        "provenance": "synthetic_fixed_sample_release_experiment",
        "model_evaluation": False,
        "positive": positive,
        "critical_regression": critical,
        "demonstration_passed": positive["gate_passed"]
        and not critical["gate_passed"]
        and bool(critical.get("critical_failed_case_ids")),
    }
