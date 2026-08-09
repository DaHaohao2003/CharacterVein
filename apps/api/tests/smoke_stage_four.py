"""Verify immutable versions and fact-layer reuse against the Docker API."""

import json
import time

import httpx


def wait_for_task(client: httpx.Client, task_id: str) -> dict[str, object]:
    for _ in range(240):
        task = client.get(f"/tasks/{task_id}").raise_for_status().json()
        if task["status"] not in {"confirmed", "running"}:
            return task
        time.sleep(1)
    raise RuntimeError("任务未在 240 秒内结束")


def main() -> None:
    with httpx.Client(base_url="http://localhost:8000/api/v1", timeout=180) as client:
        for _ in range(60):
            try:
                if client.get("/health", timeout=2).is_success:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("API did not become healthy")

        task = (
            client.post(
                "/tasks",
                json={
                    "raw_input": (
                        "为小学六年级制作4分钟的云字讲解，至少3个历史阶段，"
                        "生成2道互动题，争议不要写成定论。"
                    )
                },
            )
            .raise_for_status()
            .json()
        )
        task_id = task["id"]
        client.put(f"/tasks/{task_id}/spec", json={"spec": task["spec"]}).raise_for_status()
        client.post(f"/tasks/{task_id}/run").raise_for_status()
        result = wait_for_task(client, task_id)
        if result["status"] == "failed":
            raise RuntimeError(result["error_message"])

        before_evolution = result["evolution_package"]
        before_events = client.get(f"/tasks/{task_id}/events").raise_for_status().json()
        before_retrievals = sum(item["step"] == "evidence_retrieval" for item in before_events)
        initial_versions = client.get(f"/tasks/{task_id}/contents").raise_for_status().json()
        assert len(initial_versions) == 1

        regenerated = (
            client.post(
                f"/tasks/{task_id}/regenerate",
                json={
                    "audience": "成人文化爱好者",
                    "duration_minutes": 2,
                    "output_type": "interactive_lesson",
                    "interaction_count": 1,
                    "mode": "full",
                },
            )
            .raise_for_status()
            .json()
        )
        after = client.get(f"/tasks/{task_id}").raise_for_status().json()
        after_events = client.get(f"/tasks/{task_id}/events").raise_for_status().json()
        after_retrievals = sum(item["step"] == "evidence_retrieval" for item in after_events)

        assert regenerated["version"] == 2
        assert regenerated["evolution_hash"] == initial_versions[0]["evolution_hash"]
        assert after["evolution_package"] == before_evolution
        assert after_retrievals == before_retrievals
        assert after["spec"]["audience"] == "成人文化爱好者"
        assert after["generated_content"]["duration_minutes"] == 2

        edited_content = dict(after["generated_content"])
        edited_content["title"] = "人工编辑后的云文化讲解"
        edited = (
            client.put(
                f"/tasks/{task_id}/contents/2",
                json={"content": edited_content, "change_summary": "修改标题"},
            )
            .raise_for_status()
            .json()
        )
        assert edited["version"] == 3
        versions = client.get(f"/tasks/{task_id}/contents").raise_for_status().json()
        assert [item["version"] for item in versions] == [3, 2, 1]

        html = client.post(f"/tasks/{task_id}/exports", json={"format": "html"})
        structured = client.post(f"/tasks/{task_id}/exports", json={"format": "json"})
        html.raise_for_status()
        structured.raise_for_status()
        assert "<!doctype html>" in html.text
        assert structured.json()["content_version"] == 3
        print(
            json.dumps(
                {
                    "task_id": task_id,
                    "versions": len(versions),
                    "evolution_hash": edited["evolution_hash"],
                    "retrieval_events_before": before_retrievals,
                    "retrieval_events_after": after_retrievals,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
