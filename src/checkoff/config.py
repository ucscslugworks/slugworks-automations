"""Configuration for the check-off tools, read from common/canvas.json.

The same file already holds the Canvas token used by the access-control sync
(src/server/canvas.py reads "auth_token"), so the check-off settings live
alongside it in their own sections rather than in a second config file.

Environment overrides, useful on shared machines:
    CANVAS_TOKEN     overrides the token in the file
    CANVAS_URL       overrides the API URL
    CHECKOFF_CONFIG  points at a different config file
"""

import json
import os
from typing import Any, Dict, List, Optional

DEFAULT_API_URL = "https://canvas.ucsc.edu"

# Repository root, two levels up from src/checkoff/.
ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
COMMON = os.path.join(ROOT, "common")
DEFAULT_CONFIG_PATH = os.path.join(COMMON, "canvas.json")


class ConfigError(Exception):
    """Raised when the config is missing, malformed, or incomplete."""


class Config:
    """Parsed canvas.json with helpers for the per-command sections."""

    def __init__(self, data: Dict[str, Any], path: str):
        self.path = path
        self.data = data

    @property
    def api_url(self) -> str:
        return (
            os.environ.get("CANVAS_URL") or self.data.get("api_url") or DEFAULT_API_URL
        )

    @property
    def token(self) -> str:
        # "auth_token" is the key the access-control sync has always used.
        token = (
            os.environ.get("CANVAS_TOKEN")
            or self.data.get("auth_token")
            or self.data.get("token")
        )
        if not token:
            raise ConfigError(
                f'No Canvas token. Set CANVAS_TOKEN or add "auth_token" to {self.path}.'
            )
        return str(token)

    @property
    def course_id(self) -> int:
        value = self.data.get("course_id") or self.data.get("course")
        if not value:
            raise ConfigError(f'No "course_id" in {self.path}.')
        return int(value)

    @property
    def log_dir(self) -> str:
        return str(self.data.get("log_dir", os.path.join(ROOT, "logs", "checkoff")))

    @property
    def enrollment_types(self) -> List[str]:
        return list(self.data.get("enrollment_types", ["student"]))

    @property
    def enrollment_states(self) -> List[str]:
        return list(
            self.data.get(
                "enrollment_states", ["active", "invited", "completed", "inactive"]
            )
        )

    def section(self, name: str) -> Dict[str, Any]:
        value = self.data.get(name)
        return dict(value) if isinstance(value, dict) else {}

    def require(self, section: str, key: str) -> Any:
        value = self.section(section).get(key)
        if value in (None, "", [], {}):
            raise ConfigError(f'Missing "{section}.{key}" in {self.path}.')
        return value

    def common_path(self, filename: str) -> str:
        """Path to a file in common/, where the repo keeps its credentials."""
        return os.path.join(COMMON, filename)


def load(path: Optional[str] = None) -> Config:
    """Read the config file, failing with a message that says how to fix it."""
    path = path or os.environ.get("CHECKOFF_CONFIG") or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        raise ConfigError(
            f"Config file not found: {path} (see common.example/canvas.json)"
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object.")
    return Config(data, path)
