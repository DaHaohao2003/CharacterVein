from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from character_vein_api.database import get_session
from character_vein_api.repositories import EvidenceRepository
from character_vein_api.schemas import ClaimEvidenceResponse, ClaimResponse

router = APIRouter(prefix="/claims", tags=["claims"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.get("/{claim_id}", response_model=ClaimResponse)
async def get_claim(claim_id: str, session: SessionDependency) -> ClaimResponse:
    claim = await EvidenceRepository(session).get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="陈述不存在")
    return ClaimResponse.from_record(claim)


@router.get("/{claim_id}/evidence", response_model=list[ClaimEvidenceResponse])
async def get_claim_evidence(
    claim_id: str, session: SessionDependency
) -> list[ClaimEvidenceResponse]:
    repository = EvidenceRepository(session)
    claim = await repository.get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="陈述不存在")
    rows = await repository.claim_evidence(claim.task_id, claim.claim_id)
    return [
        ClaimEvidenceResponse(
            evidence_id=evidence.id,
            source_id=source.id,
            title=source.title,
            author_or_org=source.author_org,
            publication_date=source.publication_date,
            quote_or_summary=evidence.content,
            locator=evidence.locator,
            url=source.url,
            authority_level=source.authority_level,
            license=source.license,
            support_type=support_type,
        )
        for evidence, source, support_type in rows
    ]
