import json

from character_vein_api.services import evaluate_content_constraints, evolution_hash
from character_vein_domain import TaskSpec
from character_vein_exporters import export_html, export_json
from character_vein_providers import DeterministicAuditProvider, DeterministicTextProvider
from character_vein_workflows.fixtures import case_evolution_package


async def test_expression_regeneration_keeps_fact_layer_unchanged() -> None:
    evolution = case_evolution_package("云")
    before_hash = evolution_hash(evolution)
    provider = DeterministicTextProvider()
    first_spec = TaskSpec(target_characters=["云"], audience="小学六年级", duration_minutes=4)
    second_spec = first_spec.model_copy(
        update={"audience": "成人文化爱好者", "duration_minutes": 2}
    )

    first = await provider.generate_content(first_spec, evolution)
    second = await provider.generate_content(second_spec, evolution)

    assert first.audience == "小学六年级"
    assert second.audience == "成人文化爱好者"
    assert second.duration_minutes == 2
    assert first.body_markdown != second.body_markdown
    assert evolution_hash(evolution) == before_hash


async def test_stage_four_exports_and_constraints_are_structured() -> None:
    evolution = case_evolution_package("云")
    spec = TaskSpec(target_characters=["云"], audience="成人", duration_minutes=3)
    content = await DeterministicTextProvider().generate_content(spec, evolution)
    audit = await DeterministicAuditProvider().audit(evolution.claims, evolution.evidence, 1)
    constraints = evaluate_content_constraints(spec, evolution, content, audit)

    html = export_html(content, evolution)
    payload = json.loads(
        export_json(
            task_id="task-1",
            version=2,
            spec=spec,
            content=content,
            evolution=evolution,
            audit=audit,
        )
    )

    assert constraints.passed is True
    assert "<!doctype html>" in html
    assert "打印" not in html
    assert payload["schema_version"] == "character-vein-export-v1"
    assert payload["content_version"] == 2
    assert payload["evolution_package"]["character"] == "云"
