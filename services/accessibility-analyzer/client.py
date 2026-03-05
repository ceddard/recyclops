import httpx
import logging
import os
import base64

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "ghp_dummy_token_for_testing")
GITHUB_API = "https://api.github.com"
BYPASS_API_URL = os.environ.get("BYPASS_API_URL", "http://localhost:8001")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


async def get_pr_html_files(repo: str, pr_number: int) -> list[dict]:
    """Retorna lista de arquivos HTML modificados no PR com seu conteúdo."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files", headers=HEADERS
        )
        resp.raise_for_status()
        files = resp.json()

    html_files = []
    for f in files:
        if not f["filename"].endswith((".html", ".htm")):
            continue
        if f.get("status") == "removed":
            continue

        content = await _get_file_content(
            repo, f["filename"], f.get("contents_url", "")
        )
        if content:
            html_files.append(
                {"filename": f["filename"], "content": content, "sha": f.get("sha", "")}
            )

    logger.info(
        f"[GitHub] {len(html_files)} arquivo(s) HTML encontrado(s) no PR #{pr_number}"
    )
    return html_files


async def _get_file_content(repo: str, filepath: str, contents_url: str) -> str | None:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                contents_url or f"{GITHUB_API}/repos/{repo}/contents/{filepath}",
                headers=HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8")
        except Exception as e:
            logger.error(f"[GitHub] Erro ao buscar conteúdo de {filepath}: {e}")
    return None


async def get_push_html_files(repo: str, sha: str) -> list[dict]:
    """Retorna lista de arquivos HTML modificados no commit com seu conteúdo."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/commits/{sha}", headers=HEADERS
        )
        resp.raise_for_status()
        commit_data = resp.json()

    html_files = []
    files = commit_data.get("files", [])

    for f in files:
        if not f["filename"].endswith((".html", ".htm")):
            continue
        if f.get("status") == "removed":
            continue

        # Usar a URL de conteúdo do commit
        content = await _get_file_content(
            repo, f["filename"], f.get("contents_url", "")
        )
        if content:
            html_files.append(
                {"filename": f["filename"], "content": content, "sha": f.get("sha", "")}
            )

    logger.info(
        f"[GitHub] {len(html_files)} arquivo(s) HTML encontrado(s) no commit {sha[:7]}"
    )
    return html_files


async def create_check_run(repo: str, head_sha: str) -> int | None:
    """Cria um Check Run 'em progresso' e retorna o check_run_id. Retorna None se erro 403."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                f"{GITHUB_API}/repos/{repo}/check-runs",
                headers=HEADERS,
                json={
                    "name": "CERS-IA Accessibility",
                    "head_sha": head_sha,
                    "status": "in_progress",
                    "started_at": _now_iso(),
                    "output": {
                        "title": "Analisando acessibilidade...",
                        "summary": "O CERS-IA está processando os arquivos HTML do PR.",
                    },
                },
            )

            if resp.status_code == 403:
                logger.warning(
                    f"[GitHub] Permissão negada para criar Check Run (403) — continuando sem check run"
                )
                return None

            resp.raise_for_status()
            check_run_id = resp.json()["id"]
            logger.info(f"[GitHub] Check Run criado: #{check_run_id}")
            return check_run_id
        except Exception as e:
            logger.warning(
                f"[GitHub] Erro ao criar Check Run: {e} — continuando sem check run"
            )
            return None


async def complete_check_run(
    repo: str,
    check_run_id: int,
    conclusion: str,  # "success" | "failure"
    score: float,
    issues_count: int,
    summary_text: str,
    bypass: dict | None = None,
):
    icon = "✅" if conclusion == "success" else "❌"
    bypass_note = (
        f"\n\n> 🔓 **Bypass ativo** — Motivo: _{bypass['reason']}_ (por {bypass['created_by']})"
        if bypass
        else ""
    )

    body = f"""## {icon} CERS-IA — Relatório de Acessibilidade

**Score:** `{score:.0f} / 100`  
**Threshold:** `50 / 100`  
**Problemas encontrados:** `{issues_count}`
{bypass_note}

---

{summary_text}"""

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{GITHUB_API}/repos/{repo}/check-runs/{check_run_id}",
            headers=HEADERS,
            json={
                "status": "completed",
                "conclusion": conclusion,
                "completed_at": _now_iso(),
                "output": {
                    "title": f"Score: {score:.0f}/100 — {'Aprovado' if conclusion == 'success' else 'Reprovado'}",
                    "summary": body,
                },
            },
        )
        resp.raise_for_status()
        logger.info(f"[GitHub] Check Run #{check_run_id} finalizado: {conclusion}")


async def post_pr_review(
    repo: str,
    pr_number: int,
    score: float,
    all_issues: list[dict],
    files: list,
    passed: bool,
    bypass: dict | None,
):
    """Posta review no PR com o relatório completo e sugestões inline."""
    icon = "✅" if passed else "❌"
    bypass_note = ""
    if bypass:
        bypass_note = f"\n\n> 🔓 **Bypass ativo** — _{bypass['reason']}_ (registrado por {bypass['created_by']})\n"

    # Garante que cada issue tem severity (fallback: info)
    for issue in all_issues:
        if not issue.get("severity"):
            issue["severity"] = "info"
    
    critical = [i for i in all_issues if i.get("severity") == "critical"]
    warnings = [i for i in all_issues if i.get("severity") == "warning"]
    infos = [i for i in all_issues if i.get("severity") == "info"]

    logger.debug(f"[GitHub] Issues by severity: critical={len(critical)}, warning={len(warnings)}, info={len(infos)}")

    issues_md = ""
    if critical:
        issues_md += "\n### 🔴 Críticos\n"
        issues_md += "\n".join(
            f"- **{i['message']}** `{i.get('element','')}` — _{i.get('wcag_criterion','')}_"
            for i in critical
        )
    if warnings:
        issues_md += "\n### 🟡 Avisos\n"
        issues_md += "\n".join(
            f"- {i['message']} `{i.get('element','')}`" for i in warnings
        )
    if infos:
        issues_md += "\n### 🔵 Informações\n"
        issues_md += "\n".join(f"- {i['message']}" for i in infos)

    body = f"""## {icon} CERS-IA — Análise de Acessibilidade

| Métrica | Valor |
|---|---|
| **Score** | `{score:.0f} / 100` |
| **Threshold** | `50 / 100` |
| **Resultado** | {'✅ APROVADO' if passed else '❌ BLOQUEADO'} |
| **Críticos** | {len(critical)} |
| **Avisos** | {len(warnings)} |
| **Infos** | {len(infos)} |
{bypass_note}
{issues_md}

---
_Análise gerada pelo CERS-IA · Baseado em WCAG 2.1 e NBR 17060_"""

    # Monta inline comments com sugestões (formato GitHub Suggestion)
    review_comments = []
    total_suggestions = 0
    suggestions_with_line = 0
    
    for file_analysis in files:
        total_suggestions += len(file_analysis.suggestions)
        for suggestion in file_analysis.suggestions[:5]:  # máx 5 sugestões por arquivo
            if not suggestion.line:
                logger.warning(
                    f"[GitHub] Sugestão sem linha no arquivo {file_analysis.filename}: {suggestion.description}"
                )
                continue
            suggestions_with_line += 1
            review_comments.append(
                {
                    "path": file_analysis.filename,
                    "line": suggestion.line,
                    "body": (
                        f"♿ **CERS-IA:** {suggestion.description}\n\n"
                        f"```suggestion\n{suggestion.fixed_code}\n```"
                    ),
                }
            )
    
    logger.info(
        f"[GitHub] Total sugestões analisadas: {total_suggestions} | "
        f"Com linha definida: {suggestions_with_line} | "
        f"Comentários criados: {len(review_comments)}"
    )

    event = "REQUEST_CHANGES" if not passed else "APPROVE"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews",
            headers=HEADERS,
            json={"body": body, "event": event, "comments": review_comments},
        )
        if resp.status_code not in (200, 201):
            logger.error(
                f"[GitHub] Erro ao postar review: {resp.status_code} {resp.text}"
            )
            logger.debug(f"[GitHub] Payload enviado: body={len(body)} chars, comments={len(review_comments)}")
        else:
            logger.info(f"[GitHub] Review postado no PR #{pr_number} — evento: {event} | {len(review_comments)} sugestões inline")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def check_bypass_api(repo: str, pr_number: int) -> dict | None:
    """
    Chama a bypass-api para verificar se existe bypass ativo para este PR.
    Retorna {active: bool, reason: str, created_by: str, expires_at: int} ou None.
    """
    try:
        owner, repo_name = repo.split("/")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BYPASS_API_URL}/bypass/{owner}/{repo_name}/{pr_number}", timeout=10
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("active"):
                    logger.info(
                        f"[Bypass-API] PR #{pr_number} tem bypass ativo: {data.get('reason')}"
                    )
                    return data
            elif resp.status_code == 404:
                logger.debug(
                    f"[Bypass-API] Nenhum bypass encontrado para PR #{pr_number}"
                )
                return None
            else:
                logger.warning(
                    f"[Bypass-API] Erro ao verificar bypass: {resp.status_code}"
                )
                return None
    except httpx.TimeoutException:
        logger.error(f"[Bypass-API] Timeout ao verificar bypass para PR #{pr_number}")
        return None
    except Exception as e:
        logger.error(f"[Bypass-API] Erro ao chamar bypass-api: {e}")
        return None


async def post_pr_comment(
    repo: str,
    pr_number: int,
    score: float,
    issues_count: int,
    threshold: int = 50,
    passed: bool = True,
    bypass: dict | None = None,
):
    """
    Posta comentário no PR com score, resultado e bypass info.
    """
    icon = "✅" if passed else "❌"
    status_text = "APROVADO" if passed else "BLOQUEADO"

    bypass_note = ""
    if bypass:
        bypass_note = f"\n\n> 🔓 **PR Liberado por Bypass**\n> Motivo: _{bypass.get('reason')}_\n> Registrado por: @{bypass.get('created_by')}"

    body = f"""{icon} **CERS-IA — Resultado da Análise**

| Métrica | Valor |
|---|---|
| **Score** | `{score:.0f} / 100` |
| **Threshold** | `{threshold} / 100` |
| **Status** | {status_text} |
| **Problemas** | {issues_count} |
{bypass_note}

{'Analyze as acessibilidade dos seus arquivos HTML!' if issues_count == 0 else f'Encontrei {issues_count} problema(s) de acessibilidade. Verifique o Check Run para detalhes completos.'}
"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
                headers=HEADERS,
                json={"body": body},
            )
            resp.raise_for_status()
            logger.info(f"[GitHub] Comentário postado no PR #{pr_number}")
    except Exception as e:
        logger.error(f"[GitHub] Erro ao postar comentário: {e}")
