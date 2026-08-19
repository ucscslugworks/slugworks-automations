"""Copy completion grades from one course offering's assignments to another's.

Each year the course is recreated with new IDs, so returning students' check-offs
have to be carried forward.  Users are matched by Canvas id, then login_id, then
sis_user_id -- see src/canvas_util.match_user.
"""

import csv
import os
from typing import Dict, List, Optional, Tuple

from canvasapi.exceptions import CanvasException

from src import canvas_util, log
from src.checkoff.config import Config, ConfigError

logger = log.setup_logs("checkoff", log.INFO)

Pair = Tuple[str, str]  # (source assignment id-or-name, target assignment id-or-name)


# ---------------------------------------------------------------------------
# Where pairs come from
# ---------------------------------------------------------------------------


def pairs_from_csv(path: str) -> List[Pair]:
    """Read source/target pairs from a CSV.

    Accepts source_id/target_id or source_name/target_name in any combination,
    and tolerates a BOM, blank lines, and '#' comments.
    """

    def clean(value) -> str:
        if isinstance(value, list):
            value = ",".join(v for v in value if v is not None)
        return (value or "").replace("﻿", "").strip()

    pairs: List[Pair] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = (
            line for line in f if line.strip() and not line.lstrip().startswith("#")
        )
        reader = csv.DictReader(rows)
        for number, raw in enumerate(reader, start=1):
            row = {
                (k or "").replace("﻿", "").strip().lower(): clean(v)
                for k, v in raw.items()
                if k and k.strip()
            }
            source = row.get("source_id") or row.get("source_name")
            target = row.get("target_id") or row.get("target_name")
            if source and target:
                pairs.append((source, target))
            elif any(row.values()):
                print(f"Skipping malformed row #{number} in {path}: {row}")
                logger.warning("Malformed row #%d in %s: %s", number, path, row)
    return pairs


def pairs_from_args(specs: List[str]) -> List[Pair]:
    """Parse --pair SRC:TGT arguments."""
    pairs: List[Pair] = []
    for spec in specs:
        if ":" not in spec:
            raise ConfigError(f"--pair expects SOURCE:TARGET, got '{spec}'")
        source, target = spec.split(":", 1)
        pairs.append((source.strip(), target.strip()))
    return pairs


def pairs_from_config(cfg: Config) -> List[Pair]:
    raw = cfg.section("transfer").get("pairs") or []
    pairs: List[Pair] = []
    for entry in raw:
        if isinstance(entry, dict):
            pairs.append((str(entry["source"]), str(entry["target"])))
        else:
            source, target = entry
            pairs.append((str(source), str(target)))
    return pairs


# ---------------------------------------------------------------------------
# Interactive module picker
# ---------------------------------------------------------------------------


def _parse_selection(raw: str, count: int) -> List[int]:
    """Parse '1,3 5-7' into zero-based indices."""
    picks = set()
    for token in (t for chunk in raw.split(",") for t in chunk.split()):
        if "-" in token:
            low, high = token.split("-", 1)
            if low.isdigit() and high.isdigit():
                picks.update(range(int(low) - 1, int(high)))
        elif token.isdigit():
            picks.add(int(token) - 1)
    return [i for i in sorted(picks) if 0 <= i < count]


def _choose(prompt: str, items: List[str], default_all: bool = False) -> List[int]:
    print(prompt)
    for index, item in enumerate(items, start=1):
        print(f"[{index:2d}] {item}")
    tail = "Enter = all" if default_all else "Enter = none"
    raw = input(f"\nNumbers or ranges (e.g. 1,3 5-7); {tail}: ").strip()
    if not raw:
        return list(range(len(items))) if default_all else []
    return _parse_selection(raw, len(items))


def pairs_interactive(src_course, tgt_course) -> List[Pair]:
    """Pick source modules and assignments, then match each to a target."""
    by_module: Dict[Tuple[str, int], List[Tuple[int, str]]] = {}
    for mod_name, mod_id, aid, title in canvas_util.module_assignments(src_course):
        by_module.setdefault((mod_name, mod_id), []).append((aid, title))

    if not by_module:
        print("No modules with assignments in the source course.")
        return []

    modules = list(by_module)
    chosen = _choose(
        "\nSelect source MODULES:", [f"{name} (id={mid})" for name, mid in modules]
    )
    if not chosen:
        return []

    targets = list(tgt_course.get_assignments())
    pairs: List[Pair] = []

    for index in chosen:
        key = modules[index]
        assignments = by_module[key]
        keep = _choose(
            f"\nModule '{key[0]}' -- assignments to include:",
            [f"{title} (id={aid})" for aid, title in assignments],
            default_all=True,
        )

        for aid, title in (assignments[i] for i in keep):
            match = next((t for t in targets if t.name == title), None)
            if match is not None:
                answer = (
                    input(
                        f"\n'{title}' -> target '{match.name}' (id={match.id}). Use it? [Y/n]: "
                    )
                    .strip()
                    .lower()
                )
                if answer in ("", "y", "yes"):
                    pairs.append((str(aid), str(match.id)))
                    continue

            print(f"\nPick a target for '{title}':")
            for i, t in enumerate(targets, start=1):
                print(f"[{i:2d}] {t.name}  (id={t.id}, pts={t.points_possible})")
            raw = input("Number, or Enter to skip: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(targets):
                pairs.append((str(aid), str(targets[int(raw) - 1].id)))
            else:
                print("Skipped.")

    return pairs


# ---------------------------------------------------------------------------
# The copy itself
# ---------------------------------------------------------------------------


def _collect_source(assignment, canvas) -> Dict[str, dict]:
    """Completion flags from the source assignment, keyed by source user id."""
    out: Dict[str, dict] = {}
    for sub in assignment.get_submissions(include=["user", "submission_comments"]):
        who = canvas_util.identity_of_submission(sub, canvas)
        if not who.canvas_id:
            continue

        comments = ""
        for comment in getattr(sub, "submission_comments", None) or []:
            author = comment.get("author_name") or "Instructor"
            comments += f"{author}: {comment.get('comment') or ''}\n"

        out[who.canvas_id] = {
            "identity": who,
            "complete": canvas_util.is_complete(sub),
            "comment": comments.strip(),
        }
    return out


def copy_pair(
    cfg, canvas, src_course, tgt_course, tgt_maps, pair: Pair, dry_run: bool
) -> dict:
    """Copy one source assignment's completions to one target assignment."""
    options = cfg.section("transfer")
    write_zeros = bool(options.get("write_zeros_for_incomplete", False))
    copy_comments = bool(options.get("copy_comments", False))

    src = canvas_util.resolve_assignment(src_course, pair[0])
    tgt = canvas_util.resolve_assignment(tgt_course, pair[1])

    log_lines = [
        f"Source assignment: {src.name} ({src.id}) in course {src_course.id}",
        f"Target assignment: {tgt.name} ({tgt.id}) in course {tgt_course.id}",
    ]
    print(f"\nCollecting completions from '{src.name}' ({src.id})...")
    source_rows = _collect_source(src, canvas)

    planned: List[Tuple[int, str, float, str]] = []
    missing: List[str] = []
    matched_by = {"id": 0, "login_id": 0, "sis_user_id": 0}

    for data in source_rows.values():
        score = 1.0 if data["complete"] else (0.0 if write_zeros else None)
        if score is None:
            continue

        who = data["identity"]
        target_user, key = canvas_util.match_user(tgt_maps, who)
        if target_user is None:
            missing.append(who.canvas_id)
            continue

        matched_by[key] += 1
        planned.append(
            (target_user, who.cruzid or who.login_id, score, data["comment"])
        )

    log_lines.append(
        "Matched by: id={id}, login_id={login_id}, sis_user_id={sis_user_id}".format(
            **matched_by
        )
    )
    log_lines.append(f"Planned updates (count): {len(planned)}")
    if missing:
        log_lines.append(
            f"Missing in target (by any key) count: {len(missing)}  e.g. {missing[:5]}"
        )
    log_lines.append("")

    os.makedirs(cfg.log_dir, exist_ok=True)
    log_path = os.path.join(cfg.log_dir, f"copy_{src.id}_to_{tgt.id}.log")
    result = {
        "source_assignment": src.name,
        "source_id": src.id,
        "target_assignment": tgt.name,
        "target_id": tgt.id,
        "matched_by_id": matched_by["id"],
        "matched_by_login": matched_by["login_id"],
        "matched_by_sis": matched_by["sis_user_id"],
        "missing": len(missing),
        "ok": 0,
        "fail": 0,
        "dry_run": dry_run,
    }

    if dry_run:
        preview = [
            f"{name or '<no-login>'}\t-> {score}" for _u, name, score, _c in planned
        ]
        for line in preview[:20]:
            print("  " + line)
        if len(preview) > 20:
            print(f"  ...and {len(preview) - 20} more (see {log_path}).")
        log_lines.append("Preview of intended updates (cruzid -> score):")
        log_lines.extend(preview)
        _write_log(log_path, log_lines)
        print(f"Wrote preview log: {log_path}")
        return result

    print(f"Posting {len(planned)} grades to '{tgt.name}' ({tgt.id})...")
    lines: List[str] = []
    for user_id, name, score, comment in planned:
        try:
            text = (
                f"[Copied from {src_course.id}]\n{comment}"
                if (copy_comments and comment)
                else ""
            )
            canvas_util.post_grade(tgt, user_id, score, text)
            result["ok"] += 1
            lines.append(f"OK\t{name or '<no-login>'}\t{score}")
        except CanvasException as e:
            result["fail"] += 1
            lines.append(f"FAIL\t{name or '<no-login>'}\t{score}\t{e}")

    print(f"Success: {result['ok']}  Failures: {result['fail']}")
    if result["fail"]:
        print(
            "Failures usually mean the student is not in the target assignment's 'Assign to' list."
        )

    log_lines.append("Applied updates (cruzid, score, status):")
    log_lines.extend(lines)
    _write_log(log_path, log_lines)
    logger.info(
        "Copied %s (%s) -> %s (%s): ok=%d fail=%d",
        src.name,
        src.id,
        tgt.name,
        tgt.id,
        result["ok"],
        result["fail"],
    )
    print(f"Wrote results log: {log_path}")
    return result


def _write_log(path: str, lines: List[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def write_summary(cfg: Config, results: List[dict]) -> str:
    os.makedirs(cfg.log_dir, exist_ok=True)
    path = os.path.join(cfg.log_dir, "summary.csv")
    columns = [
        "source_assignment",
        "source_id",
        "target_assignment",
        "target_id",
        "matched_by_id",
        "matched_by_login",
        "matched_by_sis",
        "missing",
        "ok",
        "fail",
        "dry_run",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "") for k in columns})
    return path


def run(
    cfg: Config,
    pairs: Optional[List[Pair]],
    dry_run: bool,
    interactive: bool = False,
    source_course_id: Optional[int] = None,
    target_course_id: Optional[int] = None,
) -> List[dict]:
    options = cfg.section("transfer")
    source_id = source_course_id or options.get("source_course_id")
    target_id = (
        target_course_id or options.get("target_course_id") or cfg.data.get("course_id")
    )
    if not source_id or not target_id:
        raise ConfigError(
            'Set "transfer.source_course_id" and "transfer.target_course_id".'
        )

    canvas = canvas_util.connect(cfg.api_url, cfg.token)
    src_course = canvas.get_course(int(source_id))
    tgt_course = canvas.get_course(int(target_id))
    print(f"Source course: {src_course.name} ({src_course.id})")
    print(f"Target course: {tgt_course.name} ({tgt_course.id})")

    if interactive:
        pairs = pairs_interactive(src_course, tgt_course)
    if not pairs:
        print("No assignment pairs to process.")
        return []

    print(f"\nMode: {'DRY-RUN' if dry_run else 'APPLY'}  --  {len(pairs)} pair(s)")
    if interactive:
        if input("Proceed? [Y/n]: ").strip().lower() not in ("", "y", "yes"):
            print("Cancelled.")
            return []

    print("\nBuilding target roster maps (id, login_id, sis_user_id)...")
    tgt_maps = canvas_util.build_user_maps(
        tgt_course, canvas, cfg.enrollment_types, cfg.enrollment_states
    )

    results = []
    for index, pair in enumerate(pairs, start=1):
        print(f"\n-- Pair #{index}: {pair[0]} -> {pair[1]}")
        try:
            results.append(
                copy_pair(cfg, canvas, src_course, tgt_course, tgt_maps, pair, dry_run)
            )
        except Exception as e:
            # Keep going through the queue.
            print(f"Pair {pair[0]} -> {pair[1]} failed: {e}")
            logger.error("Pair %s -> %s failed: %s", pair[0], pair[1], e)

    if results:
        print(f"\nSummary: {write_summary(cfg, results)}")
    return results
