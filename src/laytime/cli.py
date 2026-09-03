"""``laytime`` command line: JSON basis in, JSON result out."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine import compute_laytime


def _read(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="laytime",
        description="Compute laytime, demurrage and despatch from a JSON basis file.",
    )
    parser.add_argument("basis", help="path to a basis JSON file, or '-' for stdin")
    parser.add_argument("--compact", action="store_true", help="single-line JSON output")
    parser.add_argument("--version", action="version", version=f"laytime {__version__}")
    args = parser.parse_args(argv)

    try:
        basis = _read(args.basis)
    except (OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"laytime: cannot read basis: {exc}\n")

    try:
        result = compute_laytime(basis)
    except KeyError as exc:
        parser.exit(1, f"laytime: missing field {exc} in basis\n")

    indent = None if args.compact else 2
    sys.stdout.write(json.dumps(result, indent=indent, ensure_ascii=False) + "\n")
    return 0
