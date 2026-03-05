import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from models import BypassCreate, BypassResponse
import dynamodb as db

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Suprimir logs de health check do Uvicorn
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class HealthCheckFilterMiddleware(BaseHTTPMiddleware):
    """Filtra logs de health check para reduzir ruído."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Não loga health checks
        if request.url.path != "/health":
            logger.info(f"{request.method} {request.url.path} - {response.status_code}")
        return response


app = FastAPI(
    title="CERS-IA Bypass API",
    description="Gerenciamento de bypass para PRs bloqueados pelo score de acessibilidade",
    version="1.0.0",
)

# Adicionar middlewares
app.add_middleware(HealthCheckFilterMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "bypass-api"}


@app.post("/bypass", response_model=BypassResponse, status_code=201)
def create_bypass(payload: BypassCreate):
    """Registra um bypass para liberar um PR bloqueado."""
    item = db.create_bypass(
        repo=payload.repo,
        pr_number=payload.pr_number,
        reason=payload.reason,
        created_by=payload.created_by,
        expires_in_hours=payload.expires_in_hours,
    )
    return BypassResponse(**item)


@app.get("/bypass/{owner}/{repo_name}/{pr_number}", response_model=BypassResponse)
def get_bypass(owner: str, repo_name: str, pr_number: int):
    """Consulta se existe bypass ativo para um PR."""
    repo = f"{owner}/{repo_name}"
    item = db.get_bypass(repo, pr_number)
    if not item:
        raise HTTPException(status_code=404, detail="Nenhum bypass ativo encontrado")
    return BypassResponse(**item)


@app.delete("/bypass/{owner}/{repo_name}/{pr_number}")
def delete_bypass(owner: str, repo_name: str, pr_number: int):
    """Remove o bypass de um PR."""
    repo = f"{owner}/{repo_name}"
    deleted = db.delete_bypass(repo, pr_number)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bypass não encontrado")
    return {"message": f"Bypass do PR #{pr_number} removido com sucesso"}


@app.get("/bypass/{owner}/{repo_name}")
def list_bypasses(owner: str, repo_name: str):
    """Lista todos os bypasses ativos de um repositório."""
    repo = f"{owner}/{repo_name}"
    items = db.list_bypasses(repo)
    return {"repo": repo, "active_bypasses": items, "total": len(items)}
