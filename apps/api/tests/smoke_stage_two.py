"""Run the stage-two API smoke test against a local CharacterVein stack."""

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
    with httpx.Client(base_url="http://localhost:8000/api/v1", timeout=150) as client:
        for _ in range(60):
            try:
                if client.get("/health", timeout=2).is_success:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("API did not become healthy within 60 seconds")
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

        events = client.get(f"/tasks/{task_id}/events").raise_for_status().json()
        claim_id = result["evolution_package"]["claims"][0]["claim_id"]
        claim = client.get(f"/claims/{claim_id}").raise_for_status().json()
        evidence = client.get(f"/claims/{claim_id}/evidence").raise_for_status().json()
        summary = {
            "task_id": task_id,
            "status": result["status"],
            "sources": len(result["evolution_package"]["sources"]),
            "evidence": len(result["evolution_package"]["evidence"]),
            "claims": len(result["evolution_package"]["claims"]),
            "retrieval_attempts": len(result["retrieval_summary"]),
            "audit_status": result["audit_report"]["status"],
            "audit_model": result["audit_report"]["model"],
            "audit_fallback": result["audit_report"]["fallback_used"],
            "audit_issues": len(result["audit_report"]["issues"]),
            "constraints_passed": result["constraint_result"]["passed"],
            "events": len(events),
            "claim_api": claim["audit_status"],
            "claim_evidence_api": len(evidence),
        }
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
