"""Command line entry point: python -m src.checkout <command>.

Commands:
    run         start the checkout web app
    bootstrap   create tabs + seed dummy makerspace data in the sheet
    auth        (re)authorize Google Sheets access (copy-paste, no browser)
    roster      build the CruzID<->SIS-ID map from Canvas (for ID-card swipe)
    staff       refresh the staff list from Canvas (who may use inventory admin)
"""

import argparse
import sys

from src.checkout import config as config_module


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m src.checkout",
        description="Makerspace item / room-key / consumable checkout system.",
    )
    parser.add_argument(
        "-c", "--config", help="path to checkout.json (default common/checkout.json)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="start the checkout web app")
    p.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=5002, help="bind port (default 5002)")
    p.add_argument("--debug", action="store_true", help="Flask debug mode")

    p = sub.add_parser("bootstrap", help="seed dummy inventory into the sheet")
    p.add_argument("--force", action="store_true", help="overwrite existing data")

    sub.add_parser("auth", help="authorize Google Sheets (copy-paste flow)")

    p = sub.add_parser(
        "roster", help="build the CruzID<->SIS map from Canvas (for card swipe)"
    )
    p.add_argument(
        "--canvas-config",
        help="path to canvas.json (default common/canvas.json, as gradecheck uses)",
    )

    p = sub.add_parser(
        "staff", help="refresh who counts as staff (gates the inventory admin)"
    )
    p.add_argument(
        "--canvas-config",
        help="path to canvas.json (default common/canvas.json, as gradecheck uses)",
    )

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        cfg = config_module.load(args.config)

        if args.command == "run":
            from src.checkout import app

            app.run(host=args.host, port=args.port, debug=args.debug)
        elif args.command == "bootstrap":
            from src.checkout import bootstrap

            return bootstrap.run(cfg, force=args.force)
        elif args.command == "auth":
            # Reuse the repo's shared Google auth flow; it writes the token file
            # named in checkout.json's "sheet" section.
            from src.checkoff import sheets as gsheets

            gsheets.authorize(cfg)
        elif args.command == "roster":
            # Reuse the check-off tools' Canvas config (common/canvas.json) so
            # there's a single Canvas token/course id for the whole repo.
            from src.checkoff import config as canvas_config_module
            from src.checkout import identity

            canvas_cfg = canvas_config_module.load(args.canvas_config)
            students = identity.build_roster(canvas_cfg)
            print(
                f"Built CruzID<->SIS roster from Canvas course {canvas_cfg.course_id}: "
                f"{len(students)} students -> {identity.ROSTER_PATH}"
            )
        elif args.command == "staff":
            # Same common/staff.txt the check-off tools use: one staff list per
            # repo. Without it nobody is staff and the admin pages stay shut.
            from src.checkoff import config as canvas_config_module
            from src.checkoff import staff as staff_module
            from src.checkout import session as session_module

            canvas_cfg = canvas_config_module.load(args.canvas_config)
            members = staff_module.refresh(canvas_cfg)
            print(
                f"Staff from Canvas course {canvas_cfg.course_id}: "
                f"{len(members)} -> {session_module.STAFF_PATH}"
            )
    except config_module.ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
