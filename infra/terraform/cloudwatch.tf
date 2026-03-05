# Segredos armazenados como SecureString (nunca hardcode em variável de env)
resource "aws_ssm_parameter" "github_webhook_secret" {
  name  = "/${var.project_name}/GITHUB_WEBHOOK_SECRET"
  type  = "SecureString"
  value = var.github_webhook_secret
}

resource "aws_ssm_parameter" "github_token" {
  name  = "/${var.project_name}/GITHUB_TOKEN"
  type  = "SecureString"
  value = var.github_token
}

resource "aws_ssm_parameter" "openai_api_key" {
  name  = "/${var.project_name}/OPENAI_API_KEY"
  type  = "SecureString"
  value = var.openai_api_key
}

resource "aws_ssm_parameter" "score_threshold" {
  name  = "/${var.project_name}/SCORE_THRESHOLD"
  type  = "String"
  value = tostring(var.score_threshold)
}

resource "aws_ssm_parameter" "sqs_url" {
  name  = "/${var.project_name}/SQS_URL"
  type  = "String"
  value = aws_sqs_queue.accessibility.url
}

resource "aws_ssm_parameter" "cers_ia_url" {
  name  = "/${var.project_name}/CERS_IA_URL"
  type  = "String"
  value = "http://${aws_lb.internal.dns_name}"
}
