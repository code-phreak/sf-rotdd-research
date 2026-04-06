"""
Repository path helpers.

The `scripts/rom_path.local.txt` convention is specific to this repository,
because it is part of the public workflow we want contributors to follow.
"""

from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
SRC_DIR = PACKAGE_DIR.parent
REPO_ROOT = SRC_DIR.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
LOCAL_ROM_REF = SCRIPTS_DIR / "rom_path.local.txt"


def normalize_user_path(user_value: str) -> Path:
    """Resolve user input relative to the repository root when appropriate."""
    candidate = Path(user_value.strip())
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve()


def save_local_rom_reference(path: Path) -> None:
    """Persist a ROM path for future runs in the local reference file."""
    try:
        relative = path.resolve().relative_to(REPO_ROOT.resolve())
        text = relative.as_posix()
    except ValueError:
        text = str(path.resolve())
    LOCAL_ROM_REF.write_text(text + "\n", encoding="utf-8")


def load_local_rom_reference() -> Path | None:
    """Load the saved ROM path if the user has configured one locally."""
    if not LOCAL_ROM_REF.exists():
        return None
    saved = LOCAL_ROM_REF.read_text(encoding="utf-8").strip()
    if not saved:
        return None
    return normalize_user_path(saved)


def prompt_for_rom_path() -> Path:
    """Prompt the user for a ROM path and optionally save it for later runs."""
    print("No ROM path is configured.")
    print("Enter the relative path to your ROM from the repository root.")
    user_value = input("ROM path: ").strip()
    if not user_value:
        raise FileNotFoundError("No ROM path was provided.")

    path = normalize_user_path(user_value)
    if not path.exists():
        raise FileNotFoundError(f"ROM not found: {path}")

    save_choice = input("Save this path in scripts/rom_path.local.txt for future runs? [y/N]: ").strip().lower()
    if save_choice in {"y", "yes"}:
        save_local_rom_reference(path)
        print("Saved local ROM path.")
    return path


def resolve_rom_path(cli_path: Path | None) -> Path:
    """Choose the ROM path from the CLI, local config, or an interactive prompt."""
    if cli_path is not None:
        path = normalize_user_path(str(cli_path))
        if not path.exists():
            raise FileNotFoundError(f"ROM not found: {path}")
        return path

    try:
        saved_path = load_local_rom_reference()
    except OSError as error:
        print(f"Could not read scripts/rom_path.local.txt: {error}", file=sys.stderr)
        saved_path = None

    if saved_path is not None and saved_path.exists():
        return saved_path
    if saved_path is not None and not saved_path.exists():
        print(f"Configured ROM path is missing: {saved_path}", file=sys.stderr)

    if not sys.stdin.isatty():
        raise FileNotFoundError(
            "No ROM path is configured. Pass --rom or create scripts/rom_path.local.txt with a relative path."
        )
    return prompt_for_rom_path()
