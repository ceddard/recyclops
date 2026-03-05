# Output adicional: URL da DLQ do analyzer
output "sqs_dlq_url" {
  value       = aws_sqs_queue.analyzer_dlq.url
  description = "URL da DLQ (Dead Letter Queue) do analyzer para erros críticos"
}
