from typing import Literal, Protocol

from character_vein_domain import (
    AuditIssue,
    AuditReport,
    AuditStatus,
    Claim,
    ClaimAuditResult,
    ClaimType,
    Evidence,
    EvidenceUsability,
    SupportType,
)


class EvidenceAuditProvider(Protocol):
    async def audit(
        self, claims: list[Claim], evidence: list[Evidence], attempt: int
    ) -> AuditReport: ...


class DeterministicAuditProvider:
    model_name = "deterministic-reference-checker"

    async def audit(
        self, claims: list[Claim], evidence: list[Evidence], attempt: int
    ) -> AuditReport:
        evidence_by_id = {item.evidence_id: item for item in evidence}
        results: list[ClaimAuditResult] = []
        issues: list[AuditIssue] = []
        for claim in claims:
            relations = [
                relation
                for relation in claim.evidence_relations
                if relation.evidence_id in evidence_by_id
            ]
            valid_ids = [item.evidence_id for item in relations]
            requires_evidence = claim.claim_type != ClaimType.SYSTEM_SYNTHESIS
            if requires_evidence and not valid_ids:
                results.append(
                    ClaimAuditResult(
                        claim_id=claim.claim_id,
                        status=AuditStatus.REJECTED,
                        reason="陈述没有绑定可引用来源。",
                    )
                )
                issues.append(
                    AuditIssue(
                        issue_code="EVIDENCE_MISSING",
                        claim_id=claim.claim_id,
                        message="缺少可引用来源，需要返回检索节点。",
                        severity="error",
                        action="retry_retrieval",
                        retryable=True,
                    )
                )
                continue
            direct_ids = [
                relation.evidence_id
                for relation in relations
                if relation.support_type == SupportType.SUPPORTS
                and evidence_by_id[relation.evidence_id].usability
                in {EvidenceUsability.USABLE, EvidenceUsability.PARTIAL}
            ]
            partial_ids = [
                relation.evidence_id
                for relation in relations
                if relation.support_type == SupportType.PARTIALLY_SUPPORTS
            ]
            contradiction_ids = [
                relation.evidence_id
                for relation in relations
                if relation.support_type == SupportType.CONTRADICTS
            ]
            metadata_only_ids = [
                relation.evidence_id
                for relation in relations
                if evidence_by_id[relation.evidence_id].usability == EvidenceUsability.METADATA_ONLY
            ]
            if direct_ids and contradiction_ids:
                status = AuditStatus.DISPUTED
                reason = "引用来源之间存在冲突，生成内容必须并列说明。"
                issue_code = "CLAIM_DISPUTED"
            elif contradiction_ids:
                status = AuditStatus.DISPUTED
                reason = "现有来源记录了不同解释，生成内容必须标明分歧。"
                issue_code = "CLAIM_CONTRADICTED"
            elif direct_ids:
                status = AuditStatus.APPROVED
                reason = "陈述已绑定至少一段可定位参考正文。"
                issue_code = ""
            elif partial_ids:
                status = AuditStatus.DOWNGRADED
                reason = "现有参考资料只覆盖陈述的一部分，生成时需要限定措辞。"
                issue_code = "CLAIM_PARTIALLY_SUPPORTED"
            else:
                status = AuditStatus.REJECTED
                reason = "只有背景、书目或搜索信息，缺少可引用正文。"
                issue_code = "DIRECT_SUPPORT_MISSING"
            results.append(
                ClaimAuditResult(
                    claim_id=claim.claim_id,
                    status=status,
                    reason=reason,
                    supported_evidence_ids=direct_ids or partial_ids,
                )
            )
            if status != AuditStatus.APPROVED:
                retryable = status == AuditStatus.REJECTED and (
                    bool(metadata_only_ids) or requires_evidence
                )
                issues.append(
                    AuditIssue(
                        issue_code=issue_code,
                        claim_id=claim.claim_id,
                        message=reason,
                        severity="error" if status == AuditStatus.REJECTED else "warning",
                        action=(
                            "retry_retrieval"
                            if retryable
                            else "downgrade"
                            if status == AuditStatus.DOWNGRADED
                            else "none"
                        ),
                        retryable=retryable,
                    )
                )
        needs_retry = any(item.retryable for item in issues)
        has_limited_claims = any(item.status != AuditStatus.APPROVED for item in results)
        report_status: Literal["approved", "needs_retry", "partial"] = (
            "needs_retry" if needs_retry else "partial" if has_limited_claims else "approved"
        )
        return AuditReport(
            status=report_status,
            claim_results=results,
            issues=issues,
            model=self.model_name,
            attempt=attempt,
            summary=(
                "引用检查发现需要补充参考来源。"
                if needs_retry
                else "存在来源有限、来源冲突或缺少来源的陈述。"
                if has_limited_claims
                else "全部生成候选陈述均已绑定可定位参考来源。"
            ),
        )


class AliyunBailianAuditProvider:
    """Compatibility adapter that performs deterministic reference checks.

    The model settings remain accepted so existing configuration does not break, but the
    provider does not ask a language model to decide whether a historical statement is true.
    """

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
        return await self.fallback.audit(claims, evidence, attempt)
