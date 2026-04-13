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
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Resolve the project root (two levels up from this file: shared/codegen/generate.py)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# All JSON enum definitions live here.
ENUMS_DIR: Path = PROJECT_ROOT / "shared" / "enums"

# Add the codegen package to sys.path so the generators import cleanly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generators import python_gen, java_gen


_GENERATORS: dict[str, Callable[[dict[str, Any]], str]] = {
    "python": python_gen.generate,
    "java": java_gen.generate,
}


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

    outputs: dict[str, str] = definition.get("outputs", {})

    for lang, rel_path in outputs.items():
        generator: Callable[[dict[str, Any]], str] | None = _GENERATORS.get(lang)
        if generator is None:
            print(f"  [SKIP] No generator registered for language '{lang}'")
            continue

        source: str = generator(definition)
        out_path: Path = PROJECT_ROOT / rel_path
        # parents=True creates any missing intermediate dirs; exist_ok=True avoids
        # a race condition if another process creates the directory concurrently.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(source, encoding="utf-8")
        print(f"  [OK]   {lang:8s} → {rel_path}")


def main() -> None:
    """Entry point — process all JSON definitions or a specific file.

    With no arguments, discovers and processes every *.json file in
    ``shared/enums/``.  With one or more path arguments, processes only
    those files (useful for regenerating a single enum without touching
    the rest).
    """
    if len(sys.argv) > 1:
        # Explicit file list supplied on the command line.
        targets: list[Path] = [Path(arg).resolve() for arg in sys.argv[1:]]
    else:
        # Default: process every definition found in the enums directory.
        targets = sorted(ENUMS_DIR.glob("*.json"))

    if not targets:
        print("No JSON enum definitions found in shared/enums/")
        sys.exit(1)

    for json_path in targets:
        print(f"Processing {json_path.name}")
        process_definition(json_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
