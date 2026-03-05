import boto3
import hashlib
import hmac
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs = boto3.client("sqs")
ssm = boto3.client("ssm")

_webhook_secret_cache = None


def _get_webhook_secret() -> str:
    """
    Carrega o secret do GitHub do Parameter Store (SSM).
    Cacheia para evitar múltiplas chamadas à API.
    """
    global _webhook_secret_cache
    if not _webhook_secret_cache:
        param_name = os.environ.get("WEBHOOK_SECRET_PARAM")
        if not param_name:
            raise ValueError("WEBHOOK_SECRET_PARAM não configurado")

        param = ssm.get_parameter(Name=param_name, WithDecryption=True)
        _webhook_secret_cache = param["Parameter"]["Value"]

    return _webhook_secret_cache


def _validate_github_signature(body: str, signature: str) -> bool:
    """
    Valida a assinatura HMAC-SHA256 do GitHub.
    GitHub envia: x-hub-signature-256: sha256=<hash>
    """
    try:
        secret = _get_webhook_secret().encode()
        expected = (
            "sha256=" + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
        )
        return hmac.compare_digest(signature, expected)
    except Exception as e:
        logger.error(f"Erro ao validar assinatura: {e}")
        return False


def _handle_pull_request(payload: dict) -> dict:
    """
    Processa evento de pull_request.
    Ações relevantes: opened, synchronize, reopened
    """
    action = payload.get("action", "")

    if action not in ("opened", "synchronize", "reopened"):
        logger.info(f"Ação de PR ignorada: {action}")
        return None

    pr = payload.get("pull_request", {})
    if not pr or not pr.get("head"):
        logger.warning("Dados de PR incompletos")
        return None

    repo = payload.get("repository", {})
    if not repo:
        logger.warning("Dados de repositório incompletos")
        return None

    message = {
        "event_type": "pull_request",
        "action": action,
        "repo": repo.get("full_name"),
        "pr_number": payload.get("number"),
        "pr_title": pr.get("title"),
        "head_sha": pr.get("head", {}).get("sha"),
        "head_ref": pr.get("head", {}).get("ref"),
        "base_ref": pr.get("base", {}).get("ref"),
        "author": pr.get("user", {}).get("login"),
    }

    return message


def _handle_push(payload: dict) -> dict:
    """
    Processa evento de push.
    Pode incluir múltiplos commits, envia apenas o mais recente.
    """
    ref = payload.get("ref", "")

    if ref.startswith("refs/tags/") or not payload.get("commits"):
        logger.info(f"Push ignorado: {ref}")
        return None

    repo = payload.get("repository", {})
    commits = payload.get("commits", [])

    if not repo or not commits:
        logger.warning("Dados de push incompletos")
        return None

    latest_commit = commits[-1]

    message = {
        "event_type": "push",
        "repo": repo.get("full_name"),
        "ref": ref,  # Mantém o formato completo: refs/heads/main
        "head_sha": payload.get("head_commit", {}).get("id") or latest_commit.get("id"),
        "commit_message": latest_commit.get("message", ""),
        "author": payload.get("pusher", {}).get("name"),
        "num_commits": len(commits),
    }

    return message


def lambda_handler(event, context):
    """
    Lambda webhook para eventos do GitHub.
    """
    try:
        body = event.get("body", "")
        headers = event.get("headers", {})

        if not body:
            logger.warning("Body vazio recebido")
            return {"statusCode": 400, "body": json.dumps({"error": "Empty body"})}

        signature = headers.get("x-hub-signature-256", "")
        if not signature:
            logger.warning("Assinatura GitHub não encontrada")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Missing signature"}),
            }

        if not _validate_github_signature(body, signature):
            logger.warning("Assinatura GitHub inválida")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid signature"}),
            }

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido: {e}")
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON"})}

        event_type = headers.get("x-github-event", "")
        message = None

        if event_type == "pull_request":
            logger.info(f"Evento pull_request recebido: action={payload.get('action')}")
            message = _handle_pull_request(payload)

        elif event_type == "push":
            logger.info(f"Evento push recebido: ref={payload.get('ref')}")
            message = _handle_push(payload)

        else:
            logger.info(f"Tipo de evento não suportado: {event_type}")
            return {"statusCode": 200, "body": json.dumps({"status": "ignored"})}

        if not message:
            logger.info(f"Evento filtrado por regras internas: {event_type}")
            return {"statusCode": 200, "body": json.dumps({"status": "filtered"})}

        sqs_url = os.environ.get("SQS_URL")
        if not sqs_url:
            logger.error("SQS_URL não configurado")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "SQS_URL not configured"}),
            }
        group_id = message.get("repo", "default")

        if message.get("event_type") == "pull_request":
            dedup_id = f"{message.get('repo')}#{message.get('pr_number')}"
        else:  # push
            dedup_id = f"{message.get('repo')}#{message.get('head_sha')}"

        response = sqs.send_message(
            QueueUrl=sqs_url,
            MessageBody=json.dumps(message),
            MessageGroupId=group_id,
            MessageDeduplicationId=dedup_id,
        )

        logger.info(
            f"✅ Mensagem enfileirada | "
            f"Type: {message.get('event_type')} | "
            f"Repo: {message.get('repo')} | "
            f"SHA: {message.get('head_sha')[:8]} | "
            f"MessageId: {response.get('MessageId')}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "queued",
                    "messageId": response.get("MessageId"),
                    "event": message.get("event_type"),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Erro não tratado no webhook: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
