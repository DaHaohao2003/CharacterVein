from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote

LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
BASE_URL = "https://huggingface.co/datasets/Ran0/JieZi/resolve/main/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch missing JieZi selection files directly")
    parser.add_argument("--repo", type=Path, default=Path(".data/jiezi"))
    parser.add_argument("--manifest", type=Path, default=Path("data/jiezi/selection.json"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retries", type=int, default=5)
    return parser.parse_args()


def normalize_source_path(path: str) -> str:
    if path.startswith("images/"):
        return f"JieZi-Dataset/{path}"
    return path


def is_materialized(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        return handle.read(len(LFS_POINTER_PREFIX)) != LFS_POINTER_PREFIX


def collect_expected_paths(repo: Path, manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected: set[str] = set()
    for character in manifest["characters"]:
        for stage in character["stages"]:
            metadata_path = stage.get("metadata_path")
            if stage["availability"] != "available" or not metadata_path:
                continue
            payload = json.loads((repo / metadata_path).read_text(encoding="utf-8"))
            expected.update(normalize_source_path(item) for item in payload.get("images", []))
    return sorted(expected)


def download_one(repo: Path, relative_path: str, retries: int) -> tuple[str, int]:
    destination = repo / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = BASE_URL + quote(relative_path, safe="/")
    temporary = destination.with_name(f"{destination.name}.download-{os.getpid()}")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "CharacterVein/0.1"})
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
            if not data or data.startswith(LFS_POINTER_PREFIX):
                raise RuntimeError(f"remote returned empty or LFS pointer content: {relative_path}")
            temporary.write_bytes(data)
            temporary.replace(destination)
            return relative_path, len(data)
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            last_error = exc
            if temporary.exists():
                temporary.unlink()
            if attempt < retries:
                time.sleep(min(2**attempt, 15))
    raise RuntimeError(f"failed after {retries} attempts: {relative_path}: {last_error}")


def main() -> None:
    args = parse_args()
    expected = collect_expected_paths(args.repo, args.manifest)
    pending = [path for path in expected if not is_materialized(args.repo / path)]
    print(json.dumps({"expected": len(expected), "pending": len(pending)}, ensure_ascii=False))
    if not pending:
        return

    failures: list[str] = []
    total_bytes = 0
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(download_one, args.repo, path, args.retries): path for path in pending
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                _, size = future.result()
                total_bytes += size
                completed += 1
                if completed % 100 == 0 or completed == len(pending):
                    print(f"downloaded {completed}/{len(pending)}")
            except Exception as exc:
                failures.append(f"{path}: {exc}")

    print(
        json.dumps(
            {
                "downloaded": completed,
                "bytes": total_bytes,
                "failed": len(failures),
                "failure_examples": failures[:20],
            },
            ensure_ascii=False,
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
