import json
from typing import Protocol

import httpx

from character_vein_domain import (
    AuditIssue,
    AuditReport,
    AuditStatus,
    Claim,
    ClaimAuditResult,
    ClaimType,
    Evidence,
)


class EvidenceAuditProvider(Protocol):
    async def audit(
        self, claims: list[Claim], evidence: list[Evidence], attempt: int
    ) -> AuditReport: ...


class DeterministicAuditProvider:
    model_name = "deterministic-evidence-auditor"

    async def audit(
        self, claims: list[Claim], evidence: list[Evidence], attempt: int
    ) -> AuditReport:
        evidence_by_id = {item.evidence_id: item for item in evidence}
        results: list[ClaimAuditResult] = []
        issues: list[AuditIssue] = []
        for claim in claims:
            valid_ids = [item for item in claim.evidence_ids if item in evidence_by_id]
            requires_evidence = claim.claim_type != ClaimType.SYSTEM_SYNTHESIS
            if requires_evidence and not valid_ids:
                results.append(
                    ClaimAuditResult(
                        claim_id=claim.claim_id,
                        status=AuditStatus.REJECTED,
                        reason="事实性陈述没有绑定可用证据。",
                    )
                )
                issues.append(
                    AuditIssue(
                        issue_code="EVIDENCE_MISSING",
                        claim_id=claim.claim_id,
                        message="缺少可验证来源，需要返回检索节点。",
                        severity="error",
                        action="retry_retrieval",
                        retryable=True,
                    )
                )
                continue
            weakest = max(
                (evidence_by_id[item].authority_level for item in valid_ids),
                default=claim.evidence_grade,
            )
            status = (
                AuditStatus.DOWNGRADED
                if weakest == "D" or claim.has_conflict
                else AuditStatus.APPROVED
            )
            results.append(
                ClaimAuditResult(
                    claim_id=claim.claim_id,
                    status=status,
                    reason=(
                        "存在争议或证据等级较低，已降低表述强度。"
                        if status == AuditStatus.DOWNGRADED
                        else "绑定证据可定位，且表述强度与证据等级一致。"
                    ),
                    supported_evidence_ids=valid_ids,
                )
            )
            if status == AuditStatus.DOWNGRADED:
                issues.append(
                    AuditIssue(
                        issue_code="CLAIM_DOWNGRADED",
                        claim_id=claim.claim_id,
                        message="争议陈述已保留但降低表述强度。",
                        severity="warning",
                        action="downgrade",
                    )
                )
        needs_retry = any(item.retryable for item in issues)
        return AuditReport(
            status="needs_retry" if needs_retry else "approved",
            claim_results=results,
            issues=issues,
            model=self.model_name,
            attempt=attempt,
            summary="程序审校发现需要补充证据。" if needs_retry else "全部陈述通过程序审校。",
        )


class AliyunBailianAuditProvider:
    """OpenAI-compatible structured auditor with deterministic safety checks."""

    def __init__(
        self, api_key: str, base_url: str, model: str, timeout_seconds: float = 45
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback = DeterministicAuditProvider()

    async def audit(
        self, claims: list[Claim], evidence: list[Evidence], attempt: int
    ) -> AuditReport:
        hard_report = await self.fallback.audit(claims, evidence, attempt)
        if hard_report.status == "needs_retry":
            return hard_report
        payload = {
            "claims": [item.model_dump(mode="json") for item in claims],
            "evidence": [item.model_dump(mode="json") for item in evidence],
        }
        system_message = (
            "你是汉字文化证据审校器。仅依据给定证据判断陈述，不补充外部知识。"
            "返回 JSON 对象，字段为 status、claim_results、issues、summary。"
            "status 只能是 approved、needs_retry、partial；claim_results 每项包含 "
            "claim_id、status(approved/downgraded/rejected)、reason、supported_evidence_ids；"
            "issues 每项包含 issue_code、claim_id、message、severity(info/warning/error)、"
            "action(none/retry_retrieval/downgrade/reject)、retryable。"
            "所有 reason、message 和 summary 必须使用简体中文。"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                        ],
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
            report = AuditReport.model_validate(
                {
                    **parsed,
                    "model": self.model,
                    "prompt_version": "evidence-audit-v1",
                    "attempt": attempt,
                    "fallback_used": False,
                }
            )
            expected = {item.claim_id for item in claims}
            actual = {item.claim_id for item in report.claim_results}
            if expected != actual:
                raise ValueError("模型审校未覆盖全部陈述")
            return report
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            hard_report.fallback_used = True
            hard_report.summary = "模型审校不可用，已使用确定性审校完成。"
            return hard_report
