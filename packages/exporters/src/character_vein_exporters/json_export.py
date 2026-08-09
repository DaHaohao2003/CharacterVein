import json

from character_vein_domain import AuditReport, EvolutionPackage, GeneratedContent, TaskSpec


def export_json(
    *,
    task_id: str,
    version: int,
    spec: TaskSpec,
    content: GeneratedContent,
    evolution: EvolutionPackage,
    audit: AuditReport,
) -> str:
    payload = {
        "schema_version": "character-vein-export-v1",
        "task_id": task_id,
        "content_version": version,
        "task_spec": spec.model_dump(mode="json"),
        "content": content.model_dump(mode="json"),
        "evolution_package": evolution.model_dump(mode="json"),
        "audit_report": audit.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
