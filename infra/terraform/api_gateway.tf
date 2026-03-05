# Empacota o código da Lambda
data "archive_file" "webhook_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../services/webhook-lambda"
  output_path = "${path.module}/builds/webhook_lambda.zip"
}

resource "aws_lambda_function" "webhook" {
  function_name    = "${var.project_name}-webhook"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.webhook_lambda.output_path
  source_code_hash = data.archive_file.webhook_lambda.output_base64sha256
  timeout          = 10

  environment {
    variables = {
      SQS_URL               = aws_sqs_queue.accessibility.url
      WEBHOOK_SECRET_PARAM  = aws_ssm_parameter.github_webhook_secret.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda_webhook]
}
