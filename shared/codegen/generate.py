"""
Shared enum code generator.

Reads every JSON definition from shared/enums/ and writes the generated
Python and Java enum files to the paths declared inside each JSON.

Usage (run from the project root):
    python shared/codegen/generate.py

Or generate a single file:
    python shared/codegen/generate.py shared/enums/channel.json
"""

import json
import os
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Resolve the project root (two levels up from this file: shared/codegen/generate.py)
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_ANDROID_ENUMS_PATH: Path = _PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "example" / "android" / "enums"
_DESKTOP_ENUMS_PATH: Path = _PROJECT_ROOT / "desktop" / "domain" / "enums"

_ANDROID_JSON_PATH: Path = _PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "example" / "android" / "jsons"
_DESKTOP_JSON_PATH: Path = _PROJECT_ROOT / "desktop" / "serializers" / "jsons"

# All JSON enum definitions live here.
_SHARED_DIR: Path = _PROJECT_ROOT / "shared"

_OUTPUTS: dict[str, list[Path]] = {
    "python": [_DESKTOP_ENUMS_PATH],
    "java": [_ANDROID_ENUMS_PATH],
}

_SUFFIXES: dict[str, str] = {
    "python": ".py",
    "java": ".java",
}

# Add the codegen package to sys.path so the generators import cleanly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generators import python_gen, java_gen

_GENERATORS: dict[str, Callable[[dict[str, Any]], str]] = {
    "python": python_gen.generate,
    "java": java_gen.generate,
}


def _to_snake_case(name: str) -> str:
    """Convert a PascalCase class name to a snake_case filename stem.

    Used so Python output files follow the project's ``snake_case`` convention
    (e.g. ``FileTransferChannels`` → ``file_transfer_channels``).

    Args:
        name: PascalCase enum class name.

    Returns:
        Lowercase, underscore-separated equivalent.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _save_enum(lang: str, paths: list[Path], source: str, enum_name: str) -> None:
    """Write generated enum source to every output directory for a given language.

    Args:
        lang: Target language key (e.g. ``"python"``, ``"java"``), used for
            display and to look up the file suffix from ``_SUFFIXES``.
        paths: List of destination directories in which to write the file.
        source: Fully-formed source code to write.
        enum_name: Base file name (without extension) for the output file.

    Raises:
        OSError: If an output directory cannot be created or the file cannot
            be written.
    """
    suffix = _SUFFIXES[lang]
    for path in paths:
        # parents=True creates any missing intermediate dirs; exist_ok=True avoids
        # a race condition if another process creates the directory concurrently.
        file_path = path / f"{enum_name}{suffix}"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(source, encoding="utf-8")
        print(f"  [OK]   {lang:8s} -> {path}")


def process_definition(json_path: Path) -> None:
    """Read one JSON enum definition and write all declared output files.

    Args:
        json_path: Absolute path to a shared/enums/*.json file.

    Raises:
        FileNotFoundError: If ``json_path`` does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        KeyError: If required fields (``name``, ``type``, ``members``) are absent.
        OSError: If an output directory cannot be created or the file cannot be written.
    """

    with json_path.open(encoding="utf-8") as f:
        definition: dict[str, Any] = json.load(f)
    name = definition["name"]

    for lang, paths in _OUTPUTS.items():
        generator: Callable[[dict[str, Any]], str] | None = _GENERATORS.get(lang)
        if generator is None:
            print(f"[SKIP] No generator registered for language '{lang}'")
            continue
        source: str = generator(definition)

        # Python filenames use snake_case (project convention); Java uses PascalCase.
        file_stem: str = _to_snake_case(name) if lang == "python" else name
        _save_enum(lang, paths, source, file_stem)


def main() -> None:
    """Entry point — process all JSON definitions or a specific file.

    With no arguments, discovers and processes every *.json file in
    ``shared/enums/``.  With one or more path arguments, processes only
    those files (useful for regenerating a single enum without touching
    the rest).
    """

    targets = sorted((_SHARED_DIR / "enums").glob("*.json"))

    if not targets:
        print("No JSON enum definitions found in shared/enums/")
        sys.exit(1)

    for json_path in targets:
        print(f"Processing {json_path.name}")
        process_definition(json_path)

    targets = sorted((_SHARED_DIR / "jsons").glob("*.json"))

    for target in targets:
        # shutil.copy2(str(target), str(_ANDROID_JSON_PATH))
        shutil.copy2(str(target), str(_DESKTOP_JSON_PATH / target.name))
    print("\nDone.")


if __name__ == "__main__":
    main()
