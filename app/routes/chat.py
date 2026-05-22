from fastapi import APIRouter, Depends, Request

from app.deps.auth import require_chat_user
from app.models.requests import ChatRequest
from app.models.responses import ChatResponse
from app.services.assistant_service import AssistantService

router = APIRouter()


def get_assistant_service(request: Request) -> AssistantService:
    return request.app.state.assistant_service


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    _user_id: str = Depends(require_chat_user),
    service: AssistantService = Depends(get_assistant_service),
) -> ChatResponse:
    return await service.chat(body)
