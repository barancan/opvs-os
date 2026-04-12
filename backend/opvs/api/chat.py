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
async def approve_tool_action(request_id: str) -> dict[str, str]:
    """Approve a pending tool action. Unblocks the agentic loop."""
    success = orchestrator_service.resolve_approval(request_id, approved=True)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval found for request_id: {request_id}",
        )
    return {"status": "approved", "request_id": request_id}


@router.post("/reject/{request_id}")
async def reject_tool_action(request_id: str) -> dict[str, str]:
    """Reject a pending tool action. Agentic loop continues without executing."""
    success = orchestrator_service.resolve_approval(request_id, approved=False)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval found for request_id: {request_id}",
        )
    return {"status": "rejected", "request_id": request_id}
