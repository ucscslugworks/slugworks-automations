"""Configuration for the checkout app, read from common/checkout.json.

Mirrors the src/checkoff config pattern: settings and secrets live in common/,
and Google auth reuses the shared OAuth client through src.checkoff.sheets.
The "sheet" section (credentials_file / token_file) is what that module reads.

Environment overrides:
    CHECKOUT_CONFIG           point at a different config file
    CHECKOUT_SPREADSHEET_ID   override the backing spreadsheet id
"""

import json
import os

# Reuse the repo's common/ location and error type.
from src.checkoff.config import COMMON, ConfigError

DEFAULT_CONFIG_PATH = os.path.join(COMMON, "checkout.json")

DEFAULT_TABS = {
    "items": "Items",
    "keys": "Keys",
    "consumables": "Consumables",
    "checkouts": "Checkouts",
}


class Config:
    """Parsed checkout.json with typed accessors."""

    def __init__(self, data, path):
        self.path = path
        self.data = data

    @property
    def spreadsheet_id(self) -> str:
        # Empty (not an error) when unset, so the web app can show a friendly
        # "run bootstrap" message instead of 500ing.
        return str(
            os.environ.get("CHECKOUT_SPREADSHEET_ID")
            or self.data.get("spreadsheet_id")
            or ""
        )

    @property
    def tabs(self) -> dict:
        tabs = dict(DEFAULT_TABS)
        tabs.update(self.data.get("tabs") or {})
        return tabs

    @property
    def default_checkout_days(self) -> int:
        return int(self.data.get("default_checkout_days", 7))

    @property
    def makerspace_name(self) -> str:
        return str(self.data.get("makerspace_name", "Makerspace"))

    # --- interface used by src.checkoff.sheets.get_service / authorize -------

    def section(self, name: str) -> dict:
        value = self.data.get(name)
        return dict(value) if isinstance(value, dict) else {}

    def common_path(self, filename: str) -> str:
        return os.path.join(COMMON, filename)


def load(path=None) -> Config:
    """Read the config file, failing with a message that says how to fix it."""
    path = path or os.environ.get("CHECKOUT_CONFIG") or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        raise ConfigError(
            f"Config file not found: {path} (copy common.example/checkout.json)"
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object.")
    return Config(data, path)
