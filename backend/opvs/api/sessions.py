from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from opvs.database import get_db
from opvs.models.agent_message import AgentMessage, SenderType
from opvs.models.agent_session import AgentSession, SessionStatus
from opvs.schemas.agent_message import AgentMessageCreate, AgentMessageResponse
from opvs.schemas.agent_session import AgentSessionCreate, AgentSessionResponse
from opvs.services import agent_runner
from opvs.websocket import WS_AGENT_MESSAGE, manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ── Chatroom routes (must come before /{session_uuid}) ──────────────────────

@router.get("/chatroom/messages", response_model=list[AgentMessageResponse])
async def list_chatroom_messages(
    project_id: int = Query(),
    limit: int = Query(default=50, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[AgentMessageResponse]:
    result = await db.execute(
        select(AgentMessage)
        .where(AgentMessage.project_id == project_id)
        .order_by(AgentMessage.created_at.desc())
        .limit(limit)
    )
    msgs = list(reversed(result.scalars().all()))
    return [AgentMessageResponse.model_validate(m) for m in msgs]


@router.post("/chatroom/reply", response_model=AgentMessageResponse)
async def post_user_reply(
    data: AgentMessageCreate,
    db: AsyncSession = Depends(get_db),
) -> AgentMessageResponse:
    """Post a user message to the chatroom, optionally replying to an agent question."""
    msg = AgentMessage(
        project_id=data.project_id,
        session_uuid=data.session_uuid,
        sender_type=SenderType.USER,
        sender_name="You",
        content=data.content,
        reply_to_id=data.reply_to_id,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    # If replying to an agent question, mark it resolved and unblock the agent
    if data.reply_to_id is not None:
        result = await db.execute(
            select(AgentMessage).where(AgentMessage.id == data.reply_to_id)
        )
        original = result.scalar_one_or_none()
        if original and original.requires_response:
            original.response_provided = True
            await db.commit()
            agent_runner.resolve_chatroom_response(data.reply_to_id)

    await manager.broadcast(
        WS_AGENT_MESSAGE,
        {
            "id": msg.id,
            "session_uuid": data.session_uuid,
            "sender_type": "user",
            "sender_name": "You",
            "content": data.content,
            "requires_response": False,
            "reply_to_id": data.reply_to_id,
            "created_at": msg.created_at.isoformat(),
        },
    )
    return AgentMessageResponse.model_validate(msg)


# ── Session routes ───────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentSessionResponse])
async def list_sessions(
    project_id: int | None = Query(default=None),
    status: SessionStatus | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[AgentSessionResponse]:
    query = select(AgentSession).order_by(AgentSession.created_at.desc())
    if project_id is not None:
        query = query.where(AgentSession.project_id == project_id)
    if status is not None:
        query = query.where(AgentSession.status == status)
    result = await db.execute(query)
    return [AgentSessionResponse.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=AgentSessionResponse, status_code=201)
async def spawn_session(
    data: AgentSessionCreate,
    db: AsyncSession = Depends(get_db),
) -> AgentSessionResponse:
    try:
        return await agent_runner.spawn_session(
            db, data.project_id, data.persona_id, data.task
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{session_uuid}", response_model=AgentSessionResponse)
async def get_session(
    session_uuid: str,
    db: AsyncSession = Depends(get_db),
) -> AgentSessionResponse:
    result = await db.execute(
        select(AgentSession).where(AgentSession.session_uuid == session_uuid)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return AgentSessionResponse.model_validate(session)


@router.post("/{session_uuid}/halt")
async def halt_session(session_uuid: str) -> dict[str, str]:
    success = await agent_runner.halt_session(session_uuid)
    if not success:
        raise HTTPException(status_code=404, detail="Session not running")
    return {"status": "halting", "session_uuid": session_uuid}
