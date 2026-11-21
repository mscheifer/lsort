import argparse
import difflib
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import libcst as cst

from .lsort import LSortError, sort_module


def _iter_python_files(paths: Sequence[str]) -> Iterator[Path]:
    for path in paths:
        p = Path(path)
        if p.is_dir():
            yield from sorted(p.rglob("*.py"))
        else:
            yield p


def main(argv: Sequence[str] | None) -> int:
    parser = argparse.ArgumentParser(
        prog="lsort", description="Sort dict literals marked with '# lsort'."
    )
    parser.add_argument("paths", nargs="+", help="Files or directories")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Don't write; exit 1 if any file would change",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print a unified diff instead of writing files",
    )

    # If argv is None this will read the command line args
    args = parser.parse_args(argv)

    changed = errors = 0
    for path in _iter_python_files(args.paths):
        try:
            original = path.read_bytes()
            module = cst.parse_module(original)
            new_module = sort_module(module)
        except LSortError as exc:
            print(f"{path}:{exc.line}:{exc.column}: error: {exc}", file=sys.stderr)
            errors += 1
            continue
        except cst.ParserSyntaxError as exc:
            print(f"{path}: syntax error: {exc}", file=sys.stderr)
            errors += 1
            continue

        if new_module.bytes == original:
            continue
        changed += 1

        if args.diff:
            sys.stdout.writelines(
                difflib.unified_diff(
                    module.code.splitlines(keepends=True),
                    new_module.code.splitlines(keepends=True),
                    fromfile=str(path),
                    tofile=str(path),
                )
            )
        if args.check:
            print(f"Would sort {path}")
        elif not args.diff:
            path.write_bytes(new_module.bytes)
            print(f"Sorted {path}")

    if errors:
        return 2
    return 1 if (changed and args.check) else 0


if __name__ == "__main__":
    sys.exit(main(None))
