import asyncio
import boto3
import json
import logging
import os
import signal
import sys

from analyzer import analyze_pr
from models import SQSEvent

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

SQS_URL = os.environ.get(
    "SQS_URL",
    "https://sqs.us-east-1.amazonaws.com/123456789/recyclops-accessibility.fifo",
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

sqs = boto3.client("sqs", region_name=AWS_REGION)

RUNNING = True


def shutdown(signum, frame):
    global RUNNING
    logger.info("[Worker] Sinal de shutdown recebido. Finalizando...")
    RUNNING = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


async def process_message(message: dict):
    body = json.loads(message["Body"])
    receipt = message["ReceiptHandle"]

    try:
        event = SQSEvent(**body)
    except Exception as e:
        logger.error(f"[Worker] Erro ao validar evento: {e}")
        logger.debug(f"[Worker] Payload recebido: {body}")
        # Deleta a mensagem inválida para evitar loop infinito
        sqs.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt)
        return

    logger.info(f"[Worker] Processando: {event.repo} ({event.event_type})")

    try:
        await analyze_pr(event)
        sqs.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt)
        logger.info(f"[Worker] Mensagem deletada da fila")
    except Exception as e:
        logger.error(f"[Worker] Erro ao processar evento: {e}")


async def poll_loop():
    logger.info(f"[Worker] Iniciando polling na fila: {SQS_URL}")

    while RUNNING:
        try:
            response = sqs.receive_message(
                QueueUrl=SQS_URL,
                MaxNumberOfMessages=1,  # 1 por vez (LLM é pesado)
                WaitTimeSeconds=20,  # Long polling (economiza custo)
                VisibilityTimeout=300,  # 5 min para processar
            )

            messages = response.get("Messages", [])

            if not messages:
                logger.debug("[Worker] Nenhuma mensagem na fila. Aguardando...")
                continue

            for message in messages:
                await process_message(message)

        except Exception as e:
            logger.error(f"[Worker] Erro no polling: {e}")
            await asyncio.sleep(5)  # Backoff em caso de erro

    logger.info("[Worker] Loop encerrado.")


if __name__ == "__main__":
    asyncio.run(poll_loop())
