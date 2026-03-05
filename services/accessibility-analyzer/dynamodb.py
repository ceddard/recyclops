import boto3
import logging
import os
import time
import json

logger = logging.getLogger(__name__)

dynamodb = boto3.resource(
    "dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1")
)

REPORTS_TABLE = os.environ.get("DYNAMODB_REPORTS", "recyclops-reports")
BYPASS_TABLE = os.environ.get("DYNAMODB_BYPASS", "recyclops-bypass-rules")


async def check_bypass(repo: str, pr_number: int) -> dict | None:
    table = dynamodb.Table(BYPASS_TABLE)
    try:
        resp = table.get_item(Key={"pk": f"REPO#{repo}", "sk": f"PR#{pr_number}"})
        item = resp.get("Item")
        if item:
            # Valida se não expirou manualmente (TTL do DynamoDB pode ter delay)
            if item.get("expires_at", 0) > int(time.time()):
                logger.info(
                    f"[DynamoDB] Bypass encontrado para PR #{pr_number}: {item['reason']}"
                )
                return item
    except Exception as e:
        logger.error(f"[DynamoDB] Erro ao buscar bypass: {e}")
    return None


async def save_report(
    repo: str,
    pr_number: int,
    head_sha: str,
    score: float,
    issues: list,
    bypass: dict | None,
):
    table = dynamodb.Table(REPORTS_TABLE)
    try:
        table.put_item(
            Item={
                "pk": f"REPO#{repo}",
                "sk": f"PR#{pr_number}#{head_sha[:8]}",
                "score": int(score),
                "issues_count": len(issues),
                "issues": json.dumps(issues),
                "bypass_used": bypass is not None,
                "created_at": int(time.time()),
                "expires_at": int(time.time()) + (90 * 86400),  # TTL: 90 dias
            }
        )
        logger.info(f"[DynamoDB] Relatório salvo: PR #{pr_number} | Score: {score:.0f}")
    except Exception as e:
        logger.error(f"[DynamoDB] Erro ao salvar relatório: {e}")
