resource "aws_cloudwatch_log_group" "lambda_webhook" {
  name              = "/aws/lambda/${var.project_name}-webhook"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "cers_ia" {
  name              = "/ecs/${var.project_name}/recyclops-service"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "analyzer" {
  name              = "/ecs/${var.project_name}/accessibility-analyzer"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "bypass_api" {
  name              = "/ecs/${var.project_name}/bypass-api"
  retention_in_days = 7
}

# Alarme: DLQ com mensagens (algo falhou)
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.project_name}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0

  dimensions = {
    QueueName = aws_sqs_queue.accessibility_dlq.name
  }
}
