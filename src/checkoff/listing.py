"""Read-only listings used when filling in assignment IDs in the config."""

from src import canvas_util
from src.checkoff.config import Config


def list_assignments(cfg: Config, course_id: int = None) -> None:
    canvas = canvas_util.connect(cfg.api_url, cfg.token)
    course = canvas.get_course(course_id or cfg.course_id)
    print(f"Assignments in {course.name} ({course.id}):")
    for assignment in course.get_assignments():
        print(
            f"  {assignment.id}\t{assignment.name}  (pts={assignment.points_possible})"
        )


def list_modules(cfg: Config, course_id: int = None) -> None:
    canvas = canvas_util.connect(cfg.api_url, cfg.token)
    course = canvas.get_course(course_id or cfg.course_id)
    print(f"Modules in {course.name} ({course.id}):")
    current = None
    for mod_name, mod_id, aid, title in canvas_util.module_assignments(course):
        if mod_name != current:
            current = mod_name
            print(f"\n  {mod_name} (id={mod_id})")
        print(f"    {aid}\t{title}")
