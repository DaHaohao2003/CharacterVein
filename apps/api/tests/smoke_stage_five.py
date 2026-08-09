import json
import time
from typing import Any

import httpx

API = "http://localhost:8000/api/v1"
CASES = {
    character: [f"U+{ord(character):04X}/{code}/1" for code in ("J", "B", "G", "S", "L", "K", "C")]
    for character in ("云", "雷", "礼", "明")
}


def wait_for_api(client: httpx.Client) -> None:
    for _ in range(30):
        try:
            if client.get(f"{API}/health", timeout=2).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("API did not become healthy within 30 seconds")


def wait_for_task(client: httpx.Client, task_id: str) -> dict[str, Any]:
    for _ in range(240):
        task = client.get(f"{API}/tasks/{task_id}").raise_for_status().json()
        if task["status"] not in {"confirmed", "running"}:
            return task
        time.sleep(1)
    raise RuntimeError("任务未在 240 秒内结束")


def main() -> None:
    report: dict[str, Any] = {"cases": {}, "thresholds": {"parse_s": 5, "run_s": 120}}
    with httpx.Client(timeout=180) as client:
        wait_for_api(client)
        for character, image_ids in CASES.items():
            start = time.perf_counter()
            created_response = client.post(
                f"{API}/tasks",
                json={
                    "raw_input": (
                        f"为小学六年级制作4分钟的{character}字讲解，至少3个历史阶段，"
                        "生成2道互动题，争议观点不要写成定论。"
                    )
                },
            )
            created_response.raise_for_status()
            created = created_response.json()
            parse_seconds = time.perf_counter() - start
            assert parse_seconds < 5

            task_id = created["id"]
            confirmed_response = client.put(
                f"{API}/tasks/{task_id}/spec", json={"spec": created["spec"]}
            )
            confirmed_response.raise_for_status()

            start = time.perf_counter()
            run_response = client.post(f"{API}/tasks/{task_id}/run")
            run_response.raise_for_status()
            completed = wait_for_task(client, task_id)
            run_seconds = time.perf_counter() - start
            assert run_seconds < 120
            assert completed["status"] == "completed", completed.get("error_message")
            evolution = completed["evolution_package"]
            assert evolution["character"] == character
            assert [stage["image_id"] for stage in evolution["glyph_stages"]] == image_ids
            assert all(
                stage["image_attribution"]
                for stage in evolution["glyph_stages"]
                if stage["availability"] == "available"
            )
            assert evolution["glyph_stages"][-1]["lineage_role"] == "branch"
            assert all(source["url"] and source["license"] for source in evolution["sources"])
            assert all(item.get("character") in (None, character) for item in evolution["evidence"])
            assert completed["constraint_result"]["passed"] is True

            refreshed = client.get(f"{API}/tasks/{task_id}")
            refreshed.raise_for_status()
            assert refreshed.json()["evolution_package"] == evolution
            events = client.get(f"{API}/tasks/{task_id}/events")
            events.raise_for_status()
            assert any(item["step"] == "audit" for item in events.json())
            assert any(item["step"] == "glyph_retrieval" for item in events.json())
            assert client.post(f"{API}/tasks/{task_id}/resume").status_code == 409

            report["cases"][character] = {
                "task_id": task_id,
                "parse_seconds": round(parse_seconds, 3),
                "run_seconds": round(run_seconds, 3),
                "glyph_ids": image_ids,
                "refresh_restored": True,
            }

        unsupported = client.post(f"{API}/tasks", json={"raw_input": "制作一个龙字演化讲解"})
        unsupported.raise_for_status()
        payload = unsupported.json()
        rejected = client.put(f"{API}/tasks/{payload['id']}/spec", json={"spec": payload["spec"]})
        assert rejected.status_code == 422
        report["unsupported_case_rejected"] = True

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
