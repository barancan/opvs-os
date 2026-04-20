from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import get_db
from opvs.schemas.chat import ChatMessageResponse, ChatRequest, CompactStatus
from opvs.services import orchestrator_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/history", response_model=list[ChatMessageResponse])
async def get_chat_history(
    project_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessageResponse]:
    messages = await orchestrator_service.get_history(db, project_id=project_id)
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post("", response_model=ChatMessageResponse)
async def send_chat_message(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    client_id: str = Query(default="default"),
    project_id: int | None = Query(default=None),
) -> ChatMessageResponse:
    message = await orchestrator_service.send_message(
        db, request.content, client_id, project_id=project_id
    )
    return ChatMessageResponse.model_validate(message)


@router.delete("/history")
async def clear_chat_history(
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    await orchestrator_service.clear_history(db)
    return {"cleared": True}


@router.get("/compact", response_model=CompactStatus)
async def get_compact_status(
    db: AsyncSession = Depends(get_db),
) -> CompactStatus:
    total_tokens, threshold, compacted = await orchestrator_service.get_compact_status(db)
    return CompactStatus(
        total_tokens=total_tokens,
        threshold=threshold,
        compacted=compacted,
    )


@router.post("/approve/{request_id}")
async def approve_tool_action(
    request_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Approve a pending tool action.

    If the agentic loop is live, sets the in-memory event and unblocks it.
    The DB row is updated regardless so state stays consistent.
    Returns 409 if the approval has already been resolved or expired.
    """
    from opvs.models.tool_approval import ToolApprovalStatus
    from opvs.services.approval_service import get_approval, resolve_approval_db

    # Attempt to unblock the live loop first
    live = orchestrator_service.resolve_approval(request_id, approved=True)

    # Update DB row
    row = await resolve_approval_db(db, request_id, approved=True)
    if row is not None:
        await db.commit()
        return {"status": "approved", "request_id": request_id}

    if live:
        # Event was set but DB row either doesn't exist (legacy) or was already resolved
        return {"status": "approved", "request_id": request_id}

    # Neither in-memory nor pending in DB — check why
    existing = await get_approval(db, request_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Unknown request_id: {request_id}")
    if existing.status == ToolApprovalStatus.EXPIRED:
        raise HTTPException(
            status_code=409,
            detail="Approval expired: the session was interrupted or the request timed out",
        )
    raise HTTPException(
        status_code=409,
        detail=f"Approval already {existing.status.value}",
    )


@router.post("/reject/{request_id}")
async def reject_tool_action(
    request_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Reject a pending tool action.

    Mirrors the approve endpoint: updates the live loop and DB row.
    """
    from opvs.models.tool_approval import ToolApprovalStatus
    from opvs.services.approval_service import get_approval, resolve_approval_db

    live = orchestrator_service.resolve_approval(request_id, approved=False)

    row = await resolve_approval_db(db, request_id, approved=False)
    if row is not None:
        await db.commit()
        return {"status": "rejected", "request_id": request_id}

    if live:
        return {"status": "rejected", "request_id": request_id}

    existing = await get_approval(db, request_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Unknown request_id: {request_id}")
    if existing.status == ToolApprovalStatus.EXPIRED:
        raise HTTPException(
            status_code=409,
            detail="Approval expired: the session was interrupted or the request timed out",
        )
    raise HTTPException(
        status_code=409,
        detail=f"Approval already {existing.status.value}",
    )
