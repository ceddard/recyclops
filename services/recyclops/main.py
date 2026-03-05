import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from models import InvokeRequest, InvokeResponse
from llm import CersIA

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class HealthCheckFilterMiddleware(BaseHTTPMiddleware):
    """Filtra logs de health check para reduzir ruído."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Não loga health checks, economiza logs
        if request.url.path != "/health":
            logger.info(f"{request.method} {request.url.path} - {response.status_code}")
        return response


app = FastAPI(
    title="CERS-IA Service",
    description="Serviço de análise de acessibilidade via LLM",
    version="1.0.0",
)

# Adicionar middlewares, essa porra me consumiu muito tempo pra fazer direito!!!
app.add_middleware(HealthCheckFilterMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "cers-ia"}


@app.post("/cers-ia/invoke", response_model=InvokeResponse)
async def invoke(request: InvokeRequest):
    if not request.html_content.strip():
        raise HTTPException(status_code=400, detail="html_content não pode ser vazio")

    report = await CersIA.invoke(request)

    return InvokeResponse(
        score=report.score,
        issues=report.issues,
        suggestions=report.suggestions,
        summary=report.summary,
        filename=request.pr_metadata.get("filename"),
    )
