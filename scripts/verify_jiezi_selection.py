from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the local JieZi demo subset")
    parser.add_argument("--repo", type=Path, default=Path(".data/jiezi"))
    parser.add_argument("--manifest", type=Path, default=Path("data/jiezi/selection.json"))
    parser.add_argument("--report", type=Path, default=Path("data/jiezi/import_report.json"))
    return parser.parse_args()


def normalize_source_path(path: str) -> str:
    if path.startswith("images/"):
        return f"JieZi-Dataset/{path}"
    return path


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_paths: set[str] = set()
    metadata_errors: list[str] = []

    for character in manifest["characters"]:
        for stage in character["stages"]:
            metadata_path = stage.get("metadata_path")
            if stage["availability"] != "available":
                continue
            if not metadata_path:
                metadata_errors.append(
                    f"{character['character']} {stage['script_type']}: missing metadata path"
                )
                continue
            payload = json.loads((args.repo / metadata_path).read_text(encoding="utf-8"))
            paths = [normalize_source_path(item) for item in payload.get("images", [])]
            if len(paths) != stage["image_count"]:
                metadata_errors.append(
                    f"{character['character']} {stage['script_type']}: "
                    f"manifest={stage['image_count']} metadata={len(paths)}"
                )
            expected_paths.update(paths)

    missing: list[str] = []
    pointers: list[str] = []
    total_bytes = 0
    for relative_path in sorted(expected_paths):
        path = args.repo / relative_path
        if not path.is_file():
            missing.append(relative_path)
            continue
        total_bytes += path.stat().st_size
        with path.open("rb") as handle:
            if handle.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX:
                pointers.append(relative_path)

    report: dict[str, Any] = {
        "dataset": manifest["dataset"],
        "selected_characters": len(manifest["characters"]),
        "all_seven_script_characters": sum(
            item["available_script_count"] == 7 for item in manifest["characters"]
        ),
        "expected_images": len(expected_paths),
        "materialized_images": len(expected_paths) - len(missing) - len(pointers),
        "total_bytes": total_bytes,
        "metadata_errors": metadata_errors,
        "missing_count": len(missing),
        "pointer_count": len(pointers),
        "pointer_codepoints": sorted({path.split("/")[2] for path in pointers}),
        "missing_examples": missing[:20],
        "pointer_examples": pointers[:20],
        "complete": not metadata_errors and not missing and not pointers,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
