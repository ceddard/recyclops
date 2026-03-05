# DLQ — mensagens que falharam 3x
resource "aws_sqs_queue" "accessibility_dlq" {
  name                      = "${var.project_name}-accessibility-dlq.fifo"
  fifo_queue                = true
  message_retention_seconds = 1209600 # 14 dias para análise de falhas
}

# Fila principal FIFO
resource "aws_sqs_queue" "accessibility" {
  name                        = "${var.project_name}-accessibility.fifo"
  fifo_queue                  = true
  content_based_deduplication = true
  visibility_timeout_seconds  = 300 # 5 min para processar (LLM pode ser lento)
  message_retention_seconds   = 86400 # 1 dia

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.accessibility_dlq.arn
    maxReceiveCount     = 3
  })
}
