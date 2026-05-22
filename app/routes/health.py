from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for the Next.js frontend and local dev tooling."""
    return {"status": "ok"}
