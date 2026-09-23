# Paired statistical release evaluation

This subsystem estimates changes in independently graded binary task success. It complements strict replay contracts with a fixed-sample release decision. It does not infer model quality from the included arithmetic fixture or provide sequential monitoring guarantees.

## Sampling unit and preregistration

Each case supplies one baseline/candidate pair `(B_i, C_i)` with values zero or one, computed independently by the existing oracle. The sampling assumptions are independent, identically sampled case pairs within the target population and declared slices. Pairing permits arbitrary dependence between baseline and candidate on the same case. Repeated trials for one task, customers with shared failures, and overlapping temporal observations require cluster or time-series inference instead.

`ReleasePlan` binds the experiment ID, exact labeled dataset SHA-256, system versions, slice tags, critical case IDs, allowed drop, significance level, sample minima, bootstrap count and seed. Freeze it before inspecting outcomes. Hashes make artifacts reproducible; they do not prove that a user preregistered honestly or that a collector really ran the declared version.

Complete replays are mandatory. Missing cases block the gate before constructing a paired statistical sample. The report retains every paired outcome and binds raw baseline/candidate record hashes, the plan, implementation version and dataset into an artifact hash.

## Paired estimand and exact discordance inference

The net success change is

`delta = E[C - B] = P(B=0,C=1) - P(B=1,C=0)`.

Let `b` count regressions `(1,0)`, `c` recoveries `(0,1)`, and `d=b+c`. Under the conditional McNemar null, `b | d ~ Binomial(d, 1/2)`. The deterioration p-value is `P(X >= b)`; the two-sided value is `min(1, 2 min(P(X <= b), P(X >= b)))`. Integer combinatorial sums are used, with exact numerators and denominator `2**d` preserved when a floating-point probability underflows. No chi-square approximation is used. With no discordant pairs both p-values are one; that is not evidence of equivalence.

The global comparison and every predeclared tag slice form one deterioration-test family. Holm's step-down adjustment controls its family-wise rejection probability under arbitrary dependence between slices, given valid individual tests. Tags may overlap. Unknown tags are rejected rather than silently removed after outcomes are observed.

## Uncertainty and noninferiority

The seeded paired percentile bootstrap resamples case indices, keeping each baseline/candidate pair intact. Its intervals are pointwise descriptive intervals. They are not simultaneous slice intervals, and a sample with identical differences can produce a degenerate empirical interval even with little evidence.

Release noninferiority therefore uses a separate conservative finite-sample construction. For each of `m` declared slices, compute one-sided Clopper–Pearson bounds for regression probability `p_b` and recovery probability `p_c`, each at tail level `alpha/(2m)`. Then

`L_delta = L_CP(p_c) - U_CP(p_b)`.

A union bound across the two marginals and all slices makes these lower bounds simultaneously valid with confidence at least `1-alpha` under the binomial sampling assumptions. Numerical binomial-CDF inversion uses 55 bisection steps; zero-count bounds use the closed form. In particular, zero observed regressions still has upper probability `1 - tail_alpha**(1/n)`, so a finite unchanged sample cannot prove a zero tolerance margin.

Holm's test-family guarantee and the simultaneous-bound guarantee concern different error events; no joint `1-alpha` claim across both families is made. The release's noninferiority acceptance guarantee comes from its simultaneous lower bounds. Minimum case counts are additional operational requirements, not a power calculation or substitute for uncertainty.

## Release decision

A release passes only when all of these hold:

1. Replays are complete and the plan matches the labeled dataset.
2. Every explicit critical case passes in the candidate, including previously failing baseline critical cases.
3. Global and slice sample minima are met.
4. Every simultaneous lower bound is at least `-allowed_drop`.
5. No declared slice significantly deteriorates after Holm correction.

Insufficient evidence blocks release; it is not converted into “no regression.” Critical failures block regardless of aggregate significance. The CLI writes a reviewable artifact before returning status 1 for a blocked release. Invalid plans or dataset bindings are caller errors.

## Complexity and bounds

For `B` bootstrap replicates and slice sizes `n_s`, bootstrap work is `O(B sum(n_s))`; requests exceeding twenty million resampled pairs are rejected. There are at most sixteen declared tag slices, ten thousand corpus cases and ten thousand bootstrap replicates. Exact conditional test arithmetic is linear in the discordant tail length using bounded big integers. Numerical binomial bounds use at most 55 CDF inversions per endpoint. Reports and inputs use existing bounded import contracts.

The included 240-case experiment draws independent synthetic tasks and coupled random failure indicators from a pinned seed. It illustrates a better fictional candidate and a distinct candidate version with a critical fault. It is neither a real-provider comparison nor a validation of general production coverage. Reusing this dataset to tune or repeatedly inspect candidate releases invalidates a one-shot error interpretation; use fresh held-out data or a separately designed sequential procedure.
