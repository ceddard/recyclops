import boto3
import logging
import os
import time

logger = logging.getLogger(__name__)

dynamodb = boto3.resource(
    "dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1")
)
BYPASS_TABLE = os.environ.get("DYNAMODB_BYPASS", "recyclops-bypass-rules")


def create_bypass(
    repo: str, pr_number: int, reason: str, created_by: str, expires_in_hours: int = 24
) -> dict:
    table = dynamodb.Table(BYPASS_TABLE)
    now = int(time.time())
    expires_at = now + (expires_in_hours * 3600)

    item = {
        "pk": f"REPO#{repo}",
        "sk": f"PR#{pr_number}",
        "repo": repo,
        "pr_number": pr_number,
        "reason": reason,
        "created_by": created_by,
        "created_at": now,
        "expires_at": expires_at,
    }

    table.put_item(Item=item)
    logger.info(f"[DynamoDB] Bypass criado: {repo} PR #{pr_number} por {created_by}")
    return item


def get_bypass(repo: str, pr_number: int) -> dict | None:
    table = dynamodb.Table(BYPASS_TABLE)
    resp = table.get_item(Key={"pk": f"REPO#{repo}", "sk": f"PR#{pr_number}"})
    item = resp.get("Item")

    if item and item.get("expires_at", 0) > int(time.time()):
        return item
    return None


def delete_bypass(repo: str, pr_number: int) -> bool:
    table = dynamodb.Table(BYPASS_TABLE)
    resp = table.delete_item(
        Key={"pk": f"REPO#{repo}", "sk": f"PR#{pr_number}"}, ReturnValues="ALL_OLD"
    )
    deleted = bool(resp.get("Attributes"))
    if deleted:
        logger.info(f"[DynamoDB] Bypass removido: {repo} PR #{pr_number}")
    return deleted


def list_bypasses(repo: str) -> list[dict]:
    table = dynamodb.Table(BYPASS_TABLE)
    resp = table.query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": f"REPO#{repo}", ":prefix": "PR#"},
    )
    now = int(time.time())
    return [item for item in resp.get("Items", []) if item.get("expires_at", 0) > now]
