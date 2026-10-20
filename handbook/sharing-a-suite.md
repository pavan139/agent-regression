# Sharing a replay suite

A useful suite release contains the independent labeled cases, replay schema, baseline traces and declared comparison plan. Keep deliberate failing candidates labeled as such. Someone running the supplied negative comparison should expect exit status 1.

Before sharing:

1. Run `python scripts/check_suite.py --require-lint --wheel`.
2. Run the baseline replay and a baseline-to-itself comparison.
3. Inspect exported case text and tool results. A bounded JSON format does not make sensitive data suitable for public release.
4. Include version IDs and hashes with statistical release results. The plan records declarations; it is not external proof of preregistration.

If starting from a source archive, initialize Git when necessary, make your own commit, and connect your chosen empty repository. For example:

```bash
git remote add origin https://github.com/YOUR_USERNAME/agent-regression.git
git push -u origin main
```

Do not turn a selected-probe score into a whole-project mutation claim. Likewise, fixture success describes the deterministic agent and checker, not a model or a different production tool environment. The CI workflow checks packaging and the local suite after publishing.
