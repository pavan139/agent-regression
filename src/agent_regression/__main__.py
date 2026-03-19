"""Command-line entry points; default commands perform no network calls."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .harness import compare_replays, cases, evaluate, load_cases, load_jsonl, replay, run_agent, validate
from .statistics import ReleasePlan, release_demo, release_evaluate


def write_json(value, path):
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    print(text, end="")


def main():
    parser = argparse.ArgumentParser(description="Agent contract regression and mutation lab (offline fixture).")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "evaluate", "generate"):
        command = commands.add_parser(name)
        command.add_argument("--output")
        command.add_argument("--cases", help="Optional JSONL corpus with independent labels")
        if name == "evaluate":
            command.add_argument("--replay", help="JSONL records: one {case_id, record} per case")
            command.add_argument("--export-traces", help="Write baseline records as replayable JSONL")
    compare = commands.add_parser("compare", help="Gate candidate replay against a complete baseline")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--cases")
    compare.add_argument("--output")
    release = commands.add_parser("release", help="Preregistered fixed-sample statistical release gate")
    release.add_argument("--cases", required=True)
    release.add_argument("--baseline", required=True)
    release.add_argument("--candidate", required=True)
    release.add_argument("--plan", required=True)
    release.add_argument("--output")
    statistical_demo = commands.add_parser("release-demo", help="Reproduce a synthetic statistical release experiment")
    statistical_demo.add_argument("--output")
    statistical_demo.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if args.command == "release-demo":
        report = release_demo(args.seed)
        write_json(report, args.output)
        if not report["demonstration_passed"]:
            raise SystemExit(1)
        return
    corpus = load_cases(args.cases) if args.cases else cases()
    if args.command == "generate":
        text = "".join(json.dumps(asdict(case), sort_keys=True) + "\n" for case in corpus)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    elif args.command == "demo":
        case = corpus[0]
        baseline, mutant = run_agent(case.prompt), run_agent(case.prompt, "wrong_arguments")
        write_json(
            {
                "backend": "deterministic_fixture_agent",
                "case": asdict(case),
                "baseline": baseline,
                "baseline_failures": validate(case, baseline),
                "mutant": mutant,
                "mutant_failures": validate(case, mutant),
            },
            args.output,
        )
    elif args.command == "release":
        with Path(args.plan).open(encoding="utf-8") as source:
            text = source.read(65537)
        if len(text) > 65536:
            parser.error("Release plan exceeds 65536 characters")
        try:
            plan = ReleasePlan.from_dict(json.loads(text))
            report = release_evaluate(corpus, load_jsonl(args.baseline), load_jsonl(args.candidate), plan)
        except ValueError as exc:
            parser.error(str(exc))
        write_json(report, args.output)
        if not report["gate_passed"]:
            raise SystemExit(1)
    elif args.command == "compare":
        report = compare_replays(corpus, load_jsonl(args.baseline), load_jsonl(args.candidate))
        write_json(report, args.output)
        if not report["gate_passed"]:
            raise SystemExit(1)
    elif args.replay:
        report = replay(corpus, load_jsonl(args.replay))
        write_json(report, args.output)
        if not report["all_passed"]:
            raise SystemExit(1)
    else:
        report, records = evaluate(corpus)
        if args.export_traces:
            path = Path(args.export_traces)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in records if row["mutation"] is None), encoding="utf-8"
            )
        write_json(report, args.output)
        if not report["gate_passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
