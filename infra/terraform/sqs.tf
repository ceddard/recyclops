# ─────────────────────────────────────────
# SQS FIFO: Dead Letter Queue (DLQ) - Analyzer
# ─────────────────────────────────────────
# Para erros críticos que não conseguem ser processados
resource "aws_sqs_queue" "analyzer_dlq" {
  name = "${var.project_name}-analyzer-dlq.fifo"

  fifo_queue              = true
  content_based_deduplication = true
  message_retention_seconds   = 1209600  # 14 dias para análise posterior
  visibility_timeout_seconds  = 300      # 5 minutos

  tags = {
    Name    = "${var.project_name}-analyzer-dlq"
    Purpose = "Analyzer Error Queue"
  }
}

# ─────────────────────────────────────────
# CloudWatch Alarm: DLQ não deve ter mensagens
# ─────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "analyzer_dlq_not_empty" {
  alarm_name          = "${var.project_name}-analyzer-dlq-not-empty"
  alarm_description   = "Alerta quando DLQ do analyzer tem mensagens (erro crítico)"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 1

  dimensions = {
    QueueName = aws_sqs_queue.analyzer_dlq.name
  }

  # TODO: configurar SNS topic para notificações
  # alarm_actions = [aws_sns_topic.alerts.arn]
}
