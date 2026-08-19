"""Command line entry point: python -m src.checkoff <command>."""

import argparse
import sys
from typing import List

from src.checkoff import config as config_module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.checkoff",
        description="Canvas walkthrough check-off tools.",
    )
    parser.add_argument(
        "-c", "--config", help="path to canvas.json (default common/canvas.json)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("grade", help="grade check-offs from the staff form responses")
    p.add_argument("--dry-run", action="store_true", help="report only; touch nothing")
    p.add_argument(
        "--staff-source",
        choices=["auto", "db", "canvas", "file"],
        default="auto",
        help="where the staff allow-list comes from (default: auto)",
    )

    p = sub.add_parser("staff", help="refresh the cached staff list from Canvas")
    p.add_argument(
        "--roles", nargs="+", help="enrollment types (default: teacher ta designer)"
    )

    p = sub.add_parser("transfer", help="copy completions between course offerings")
    p.add_argument(
        "--pair",
        action="append",
        default=[],
        metavar="SRC:TGT",
        help="assignment pair, repeatable; ids or exact names",
    )
    p.add_argument(
        "--pairs-csv", help="CSV with source_id/target_id (or _name) columns"
    )
    p.add_argument(
        "--interactive", action="store_true", help="pick modules and match by name"
    )
    p.add_argument(
        "--source-course", type=int, help="override transfer.source_course_id"
    )
    p.add_argument(
        "--target-course", type=int, help="override transfer.target_course_id"
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write grades to Canvas")
    mode.add_argument("--dry-run", action="store_true", help="preview only")

    p = sub.add_parser("report", help="export a CSV of completions in a date window")
    p.add_argument(
        "--course",
        type=int,
        action="append",
        default=[],
        help="course id, repeatable (default: report.courses or course_id)",
    )
    p.add_argument("--start", help="YYYY-MM-DD (default: report.start)")
    p.add_argument("--end", help="YYYY-MM-DD (default: report.end)")
    p.add_argument(
        "--assignments",
        type=int,
        nargs="+",
        help="explicit assignment ids instead of a module scan",
    )
    p.add_argument(
        "--modules", nargs="+", metavar="TERM", help="module name substrings to scan"
    )
    p.add_argument("--out", help="output CSV path (single course only)")

    p = sub.add_parser("assignments", help="list a course's assignments and their ids")
    p.add_argument("--course", type=int)

    p = sub.add_parser("modules", help="list a course's modules and their assignments")
    p.add_argument("--course", type=int)

    return parser


def _run_report(cfg, args) -> None:
    from src.checkoff import report

    options = cfg.section("report")
    courses: List = args.course or options.get("courses") or [cfg.course_id]
    if isinstance(courses, int):
        courses = [courses]

    for entry in courses:
        # A config entry may be a bare id or {"id":…, "start":…, "end":…, "assignments":[…]}
        if isinstance(entry, dict):
            course_id = int(entry["id"])
            start = args.start or entry.get("start") or options.get("start")
            end = args.end or entry.get("end") or options.get("end")
            assignments = args.assignments or entry.get("assignments")
        else:
            course_id = int(entry)
            start = args.start or options.get("start")
            end = args.end or options.get("end")
            assignments = args.assignments or options.get("assignments")

        if not start or not end:
            raise config_module.ConfigError(
                "Need a date window: pass --start/--end or set report.start/report.end."
            )

        print(f"\n=== Report for course {course_id} ({start} -> {end}) ===")
        rows = report.gather(
            cfg,
            course_id,
            start,
            end,
            assignment_ids=assignments,
            module_terms=args.modules or options.get("module_terms"),
        )
        out = (
            args.out
            if (args.out and len(courses) == 1)
            else report.default_path(cfg, course_id, start, end)
        )
        report.write_csv(rows, out)


def _run_transfer(cfg, args) -> None:
    from src.checkoff import transfer

    pairs = []
    if args.pair:
        pairs += transfer.pairs_from_args(args.pair)
    if args.pairs_csv:
        pairs += transfer.pairs_from_csv(args.pairs_csv)
    if not pairs and not args.interactive:
        pairs = transfer.pairs_from_config(cfg)

    # Dry run is the default; --apply is the deliberate opt-in to writing grades.
    dry_run = not args.apply or args.dry_run

    transfer.run(
        cfg,
        pairs,
        dry_run,
        interactive=args.interactive,
        source_course_id=args.source_course,
        target_course_id=args.target_course,
    )


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cfg = config_module.load(args.config)

        if args.command == "grade":
            from src.checkoff import grade

            grade.run(cfg, dry_run=args.dry_run, staff_source=args.staff_source)
        elif args.command == "staff":
            from src.checkoff import staff

            members = staff.refresh(cfg, roles=args.roles)
            print(f"Staff list ({len(members)}): {', '.join(members.members)}")
        elif args.command == "transfer":
            _run_transfer(cfg, args)
        elif args.command == "report":
            _run_report(cfg, args)
        elif args.command == "assignments":
            from src.checkoff import listing

            listing.list_assignments(cfg, args.course)
        elif args.command == "modules":
            from src.checkoff import listing

            listing.list_modules(cfg, args.course)
    except config_module.ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
