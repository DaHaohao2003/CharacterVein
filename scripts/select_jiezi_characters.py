from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_CODES = {
    "甲骨文": "J",
    "金文": "B",
    "战国文字": "G",
    "篆书": "S",
    "隶书": "L",
    "楷书": "K",
    "草书": "C",
}
DEMO_CHARACTERS = ("云", "雷", "礼", "明")
MANDATORY = DEMO_CHARACTERS
CURATED_PRIORITY = tuple(
    dict.fromkeys(
        "人天地日月山水火木金土雨云雷电龙虎鸟鱼马牛羊犬豕象龟鹿凤"
        "父母子女兄弟家国王后帝民士农工商兵车舟门户室宫城邑道行来去"
        "上下左右中东西南北大小多少长短高低内外前后古今春夏秋冬年时"
        "一二三四五六七八九十百千万甲乙丙丁文武礼乐仁义智信德善美爱"
        "心目耳口手足身首面言语书学教师生朋友君臣宗祖神鬼祭福祸生死"
        "食饮酒米麦田禾竹丝衣玉石贝鼎器刀剑弓矢网门林森光明黑白红黄"
        "青华安宁和同正平太永万有无成败兴亡开闭出入立坐走止见闻思知"
        "龙车家鼎"
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select the reproducible JieZi demo subset")
    parser.add_argument("--repo", type=Path, default=Path(".data/jiezi"))
    parser.add_argument("--output", type=Path, default=Path("data/jiezi/selection.json"))
    parser.add_argument("--count", type=int, default=len(DEMO_CHARACTERS))
    parser.add_argument("--complete-quota", type=int, default=len(DEMO_CHARACTERS))
    return parser.parse_args()


def character_from_metadata(path: Path, script: str) -> str:
    suffix = f"_{script}"
    if not path.stem.endswith(suffix):
        raise ValueError(f"unexpected JieZi metadata filename: {path}")
    return path.stem[: -len(suffix)]


def is_gb2312_level_one(character: str) -> bool:
    if len(character) != 1:
        return False
    try:
        encoded = character.encode("gb2312")
    except UnicodeEncodeError:
        return False
    return len(encoded) == 2 and 0xB0 <= encoded[0] <= 0xD7


def normalized_source_path(path: str) -> str:
    if path.startswith("images/"):
        return f"JieZi-Dataset/{path}"
    return path


def discover_catalog(repo: Path) -> dict[str, dict[str, Path]]:
    metadata_root = repo / "metadata"
    catalog: dict[str, dict[str, Path]] = {}
    for script in SCRIPT_CODES:
        script_root = metadata_root / script
        if not script_root.is_dir():
            raise FileNotFoundError(f"missing JieZi metadata directory: {script_root}")
        for path in script_root.glob("*.json"):
            character = character_from_metadata(path, script)
            catalog.setdefault(character, {})[script] = path
    return catalog


def rank_key(character: str, catalog: dict[str, dict[str, Path]]) -> tuple[int, int, int, str]:
    stages = catalog[character]
    metadata_size = sum(path.stat().st_size for path in stages.values())
    curated_rank = CURATED_PRIORITY.index(character) if character in CURATED_PRIORITY else 10_000
    return (-len(stages), curated_rank, -metadata_size, character)


def select_characters(
    catalog: dict[str, dict[str, Path]], count: int, complete_quota: int
) -> list[tuple[str, str]]:
    if count < len(MANDATORY):
        raise ValueError("selection count is smaller than the mandatory character count")

    selected: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(character: str, tier: str) -> None:
        if character in catalog and character not in seen and len(selected) < count:
            selected.append((character, tier))
            seen.add(character)

    for character in MANDATORY:
        if len(catalog.get(character, {})) != len(SCRIPT_CODES):
            raise ValueError(f"demo character does not cover all seven script classes: {character}")
        add(character, "mandatory_demo")

    complete = [
        character
        for character, stages in catalog.items()
        if len(stages) == len(SCRIPT_CODES) and len(character) == 1
    ]
    complete.sort(
        key=lambda character: (
            not is_gb2312_level_one(character),
            rank_key(character, catalog),
        )
    )
    for character in complete[:complete_quota]:
        add(character, "all_seven_scripts")

    for character in CURATED_PRIORITY:
        if character in catalog and len(catalog[character]) >= 4:
            add(character, "curated_common")

    remaining = [
        character
        for character in catalog
        if character not in seen and len(character) == 1 and is_gb2312_level_one(character)
    ]
    remaining.sort(key=lambda character: rank_key(character, catalog))
    for character in remaining:
        add(character, "coverage_ranked_common")

    fallback = [character for character in catalog if character not in seen and len(character) == 1]
    fallback.sort(key=lambda character: rank_key(character, catalog))
    for character in fallback:
        add(character, "coverage_ranked_fallback")

    if len(selected) != count:
        raise RuntimeError(f"could only select {len(selected)} of {count} requested characters")
    return selected


def build_manifest(
    repo: Path,
    catalog: dict[str, dict[str, Path]],
    selected: list[tuple[str, str]],
) -> dict[str, Any]:
    characters: list[dict[str, Any]] = []
    for character, tier in selected:
        stages = catalog[character]
        stage_entries: list[dict[str, Any]] = []
        for script, code in SCRIPT_CODES.items():
            metadata_path = stages.get(script)
            if metadata_path is None:
                stage_entries.append(
                    {
                        "script_type": script,
                        "script_code": code,
                        "availability": "dataset_gap",
                        "metadata_path": None,
                        "image_count": 0,
                        "image_paths": [],
                        "representative_source_path": None,
                    }
                )
                continue
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            images = [normalized_source_path(item) for item in payload.get("images", [])]
            stage_entries.append(
                {
                    "script_type": script,
                    "script_code": code,
                    "availability": "available",
                    "metadata_path": metadata_path.relative_to(repo).as_posix(),
                    "image_count": len(images),
                    "image_paths": images,
                    "representative_source_path": images[0] if images else None,
                    "structure": payload.get("structure", ""),
                    "special_structure": payload.get("special_structure", ""),
                    "evolution": payload.get("evolution", ""),
                    "original_meaning": payload.get("original_meaning", ""),
                }
            )
        characters.append(
            {
                "character": character,
                "codepoint": f"U+{ord(character):04X}",
                "selection_tier": tier,
                "available_script_count": sum(
                    stage["availability"] == "available" for stage in stage_entries
                ),
                "total_image_count": sum(stage["image_count"] for stage in stage_entries),
                "stages": stage_entries,
            }
        )

    coverage = Counter(item["available_script_count"] for item in characters)
    return {
        "dataset": "Ran0/JieZi",
        "dataset_revision": "main",
        "license": "CC BY-NC-ND 4.0; non-commercial research only",
        "selection_policy": {
            "requested_count": len(characters),
            "mandatory_characters": list(MANDATORY),
            "all_seven_script_quota": sum(
                item["available_script_count"] == len(SCRIPT_CODES) for item in characters
            ),
            "ranking": (
                "four semantically meaningful demo characters with all seven JieZi script classes"
            ),
        },
        "coverage_summary": {str(key): coverage[key] for key in sorted(coverage)},
        "total_selected_images": sum(item["total_image_count"] for item in characters),
        "characters": characters,
    }


def main() -> None:
    args = parse_args()
    catalog = discover_catalog(args.repo)
    selected = select_characters(catalog, args.count, args.complete_quota)
    manifest = build_manifest(args.repo, catalog, selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "selected": len(manifest["characters"]),
                "all_seven": manifest["selection_policy"]["all_seven_script_quota"],
                "images": manifest["total_selected_images"],
                "coverage": manifest["coverage_summary"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
