import httpx
import logging
import os
import json
import boto3
from models import SQSEvent, FileAnalysis, AnalysisResult
import client as github
import dynamodb as db

logger = logging.getLogger(__name__)

CERS_IA_URL = os.environ.get("CERS_IA_URL", "http://localhost:8000")
SCORE_THRESHOLD = int(os.environ.get("SCORE_THRESHOLD", "50"))
DLQ_URL = os.environ.get("DLQ_URL", "")

sqs_client = (
    boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    if DLQ_URL
    else None
)


async def analyze_pr(event: SQSEvent) -> AnalysisResult:
    """Processa análise de PR ou push event."""
    if event.event_type == "pull_request":
        return await _analyze_pull_request(event)
    elif event.event_type == "push":
        return await _analyze_push(event)
    else:
        raise ValueError(f"Tipo de evento não suportado: {event.event_type}")


async def _analyze_pull_request(event: SQSEvent) -> AnalysisResult:
    """Analisa arquivos HTML alterados em um PR."""
    repo = event.repo
    pr_number = event.pr_number
    head_sha = event.head_sha

    logger.info(f"[Analyzer] Iniciando análise de PR: {repo} PR #{pr_number}")

    try:
        check_run_id = await github.create_check_run(repo, head_sha)

        html_files = await github.get_pr_html_files(repo, pr_number)

        if not html_files:
            logger.warning(
                f"[Analyzer] Nenhum arquivo HTML encontrado no PR #{pr_number}"
            )
            await github.post_pr_comment(
                repo, pr_number, 100, 0, SCORE_THRESHOLD, passed=True
            )
            if check_run_id:
                await github.complete_check_run(
                    repo,
                    check_run_id,
                    "success",
                    100,
                    0,
                    "Nenhum arquivo HTML encontrado neste PR. Nada a analisar.",
                )
            return AnalysisResult(
                repo=repo,
                pr_number=pr_number,
                head_sha=head_sha,
                avg_score=100,
                files_analyzed=0,
                all_issues=[],
                files=[],
                passed=True,
            )

        files_result: list[FileAnalysis] = []  # Analisar cada arquivo via CERS-IA
        all_issues: list[dict] = []

        async with httpx.AsyncClient(timeout=120) as client:
            for html_file in html_files:
                logger.info(
                    f"[Analyzer] Chamando CERS-IA para: {html_file['filename']}"
                )
                try:
                    logger.debug(
                        f"[Analyzer] POST {CERS_IA_URL}/cers-ia/invoke | timeout=120s"
                    )
                    resp = await client.post(
                        f"{CERS_IA_URL}/cers-ia/invoke",
                        json={
                            "html_content": html_file["content"],
                            "pr_metadata": {"filename": html_file["filename"]},
                        },
                    )
                    logger.debug(f"[Analyzer] Response HTTP {resp.status_code}")
                    resp.raise_for_status()
                    data = resp.json()
                    logger.debug(f"[Analyzer] Response keys: {list(data.keys())}")

                    # Garantir que issues e suggestions são listas de dicts (não objetos Pydantic)
                    issues = [i.dict() if hasattr(i, 'dict') else i for i in data["issues"]]
                    suggestions = [s.dict() if hasattr(s, 'dict') else s for s in data["suggestions"]]

                    file_analysis = FileAnalysis(
                        filename=html_file["filename"],
                        score=data["score"],
                        issues=issues,
                        suggestions=suggestions,
                        summary=data["summary"],
                    )
                    files_result.append(file_analysis)
                    all_issues.extend(issues)
                    logger.info(
                        f"[Analyzer] {html_file['filename']}: {data['score']}/100 | "
                        f"Issues: {len(issues)} | Sugestões: {len(suggestions)}"
                    )
                    logger.debug(
                        f"[Analyzer] Issues severity: "
                        f"critical={len([i for i in issues if i.get('severity') == 'critical'])}, "
                        f"warning={len([i for i in issues if i.get('severity') == 'warning'])}, "
                        f"info={len([i for i in issues if i.get('severity') == 'info'])}"
                    )
                    logger.debug(
                        f"[Analyzer] Sugestões com line: "
                        f"{len([s for s in suggestions if s.get('line')])}/{len(suggestions)}"
                    )

                except Exception as e:
                    logger.error(
                        f"[Analyzer] {html_file['filename']}: {type(e).__name__}: {e}",
                        exc_info=True,
                    )
                    files_result.append(
                        FileAnalysis(
                            filename=html_file["filename"],
                            score=0,
                            issues=[],
                            suggestions=[],
                            summary=f"Erro ao processar arquivo: {str(e)}",
                        )
                    )

        scores = [f.score for f in files_result]
        avg_score = sum(scores) / len(scores) if scores else 0

        bypass_local = await db.check_bypass(repo, pr_number)
        logger.info(f"[Analyzer] Bypass local: {bypass_local}")

        bypass_remote = None
        if avg_score < SCORE_THRESHOLD:
            logger.info(
                f"[Analyzer] Score {avg_score:.0f} abaixo do threshold {SCORE_THRESHOLD}. Verificando bypass-api..."
            )
            bypass_remote = await github.check_bypass_api(repo, pr_number)

        bypass = bypass_remote or bypass_local

        passed = avg_score >= SCORE_THRESHOLD or bypass is not None
        conclusion = "success" if passed else "failure"

        logger.info(
            f"[Analyzer] Score: {avg_score:.0f} | Bypass: {bypass is not None} | Passou: {passed}"
        )

        await db.save_report(repo, pr_number, head_sha, avg_score, all_issues, bypass)

        await github.post_pr_comment(
            repo, pr_number, avg_score, len(all_issues), SCORE_THRESHOLD, passed, bypass
        )

        await github.post_pr_review(
            repo, pr_number, avg_score, all_issues, files_result, passed, bypass
        )

        if check_run_id:
            summaries = "\n\n".join(
                f"**{f.filename}** — Score: {f.score}/100\n{f.summary}"
                for f in files_result
            )
            await github.complete_check_run(
                repo,
                check_run_id,
                conclusion,
                avg_score,
                len(all_issues),
                summaries,
                bypass,
            )
        else:
            logger.info(
                "[Analyzer] Pulando Check Run (não foi criado por falta de permissão)"
            )

        logger.info(
            f"[Analyzer] Concluído: PR #{pr_number} | Score: {avg_score:.0f} | Resultado: {conclusion}"
        )

        return AnalysisResult(
            repo=repo,
            pr_number=pr_number,
            head_sha=head_sha,
            avg_score=avg_score,
            files_analyzed=len(files_result),
            all_issues=all_issues,
            files=files_result,
            passed=passed,
            bypass=bypass,
        )

    except Exception as e:
        logger.error(
            f"[Analyzer] Erro crítico na análise de PR #{pr_number}: {e}", exc_info=True
        )
        await _send_to_dlq(event, str(e))
        raise


async def _analyze_push(event: SQSEvent) -> AnalysisResult:
    """Analisa arquivos HTML alterados em um push commit."""
    repo = event.repo
    head_sha = event.head_sha
    ref = event.ref or "unknown"

    logger.info(f"[Analyzer] Iniciando análise de push: {repo} {ref} ({head_sha[:7]})")

    try:
        check_run_id = await github.create_check_run(repo, head_sha)

        html_files = await github.get_push_html_files(repo, head_sha)

        if not html_files:
            logger.warning(
                f"[Analyzer] Nenhum arquivo HTML encontrado no commit {head_sha[:7]}"
            )
            if check_run_id:
                await github.complete_check_run(
                    repo,
                    check_run_id,
                    "success",
                    100,
                    0,
                    "Nenhum arquivo HTML encontrado neste commit. Nada a analisar.",
                )
            return AnalysisResult(
                repo=repo,
                pr_number=None,
                head_sha=head_sha,
                avg_score=100,
                files_analyzed=0,
                all_issues=[],
                files=[],
                passed=True,
            )

        files_result: list[FileAnalysis] = []  # Analisar cada arquivo via CERS-IA
        all_issues: list[dict] = []

        async with httpx.AsyncClient(timeout=120) as client:
            for html_file in html_files:
                logger.info(
                    f"[Analyzer] Chamando CERS-IA para: {html_file['filename']}"
                )
                try:
                    logger.debug(
                        f"[Analyzer] POST {CERS_IA_URL}/cers-ia/invoke | timeout=120s"
                    )
                    resp = await client.post(
                        f"{CERS_IA_URL}/cers-ia/invoke",
                        json={
                            "html_content": html_file["content"],
                            "pr_metadata": {"filename": html_file["filename"]},
                        },
                    )
                    logger.debug(f"[Analyzer] Response HTTP {resp.status_code}")
                    resp.raise_for_status()
                    data = resp.json()
                    logger.debug(f"[Analyzer] Response keys: {list(data.keys())}")

                    file_analysis = FileAnalysis(
                        filename=html_file["filename"],
                        score=data["score"],
                        issues=data["issues"],
                        suggestions=data["suggestions"],
                        summary=data["summary"],
                    )
                    files_result.append(file_analysis)
                    all_issues.extend(data["issues"])
                    logger.info(
                        f"[Analyzer] {html_file['filename']}: {data['score']}/100"
                    )

                except Exception as e:
                    logger.error(
                        f"[Analyzer] {html_file['filename']}: {type(e).__name__}: {e}",
                        exc_info=True,
                    )
                    files_result.append(
                        FileAnalysis(
                            filename=html_file["filename"],
                            score=0,
                            issues=[],
                            suggestions=[],
                            summary=f"Erro ao processar arquivo: {str(e)}",
                        )
                    )

        scores = [f.score for f in files_result]
        avg_score = sum(scores) / len(scores) if scores else 0

        passed = avg_score >= SCORE_THRESHOLD
        conclusion = "success" if passed else "neutral"  # não bloqueia push

        logger.info(f"[Analyzer] Score: {avg_score:.0f} | Passou: {passed}")

        if check_run_id:
            summaries = "\n\n".join(
                f"**{f.filename}** — Score: {f.score}/100\n{f.summary}"
                for f in files_result
            )
            status_msg = (
                " Acessibilidade OK" if passed else f" Score baixo ({avg_score:.0f})"
            )
            await github.complete_check_run(
                repo,
                check_run_id,
                conclusion,
                avg_score,
                len(all_issues),
                f"{status_msg}\n\n{summaries}",
            )
        else:
            logger.info(
                "[Analyzer] Pulando Check Run (não foi criado por falta de permissão)"
            )

        logger.info(
            f"[Analyzer] Concluído: Push {head_sha[:7]} | Score: {avg_score:.0f}"
        )

        return AnalysisResult(
            repo=repo,
            pr_number=None,
            head_sha=head_sha,
            avg_score=avg_score,
            files_analyzed=len(files_result),
            all_issues=all_issues,
            files=files_result,
            passed=passed,
        )

    except Exception as e:
        logger.error(
            f"[Analyzer] Erro crítico na análise de push {head_sha[:7]}: {e}",
            exc_info=True,
        )
        await _send_to_dlq(event, str(e))
        raise


async def _send_to_dlq(event: SQSEvent, error: str):
    """Envia mensagem para DLQ em caso de erro crítico."""
    if not DLQ_URL or not sqs_client:
        logger.warning("[DLQ] DLQ não configurado, erro não foi enfileirado")
        return

    try:
        import time

        message = {
            "repo": event.repo,
            "pr_number": event.pr_number,
            "head_sha": event.head_sha,
            "error": error,
            "timestamp": int(time.time()),
        }

        sqs_client.send_message(
            QueueUrl=DLQ_URL,
            MessageBody=json.dumps(message),
            MessageGroupId=f"{event.repo}#{event.pr_number}",
            MessageDeduplicationId=f"{event.repo}#{event.pr_number}#{int(time.time())}",
        )
        logger.info(
            f"[DLQ] Mensagem de erro enviada para DLQ para PR #{event.pr_number}"
        )
    except Exception as dlq_error:
        logger.error(f"[DLQ] Erro ao enviar para DLQ: {dlq_error}")
