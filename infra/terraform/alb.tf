# ─────────────────────────────────────────
# API Gateway — Webhook do GitHub
# ─────────────────────────────────────────
resource "aws_apigatewayv2_api" "webhook" {
  name          = "${var.project_name}-webhook"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "webhook_lambda" {
  api_id                 = aws_apigatewayv2_api.webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.webhook.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook_post" {
  api_id    = aws_apigatewayv2_api.webhook.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.webhook_lambda.id}"
}

resource "aws_apigatewayv2_stage" "webhook" {
  api_id      = aws_apigatewayv2_api.webhook.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw_webhook" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.webhook.execution_arn}/*"
}

# ─────────────────────────────────────────
# API Gateway — Bypass API (aponta para ECS via ALB)
# ─────────────────────────────────────────
resource "aws_apigatewayv2_api" "bypass" {
  name          = "${var.project_name}-bypass-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_vpc_link" "bypass" {
  name               = "${var.project_name}-vpc-link"
  security_group_ids = [aws_security_group.alb_internal.id]
  subnet_ids         = aws_subnet.public[*].id
}

resource "aws_apigatewayv2_integration" "bypass_alb" {
  api_id             = aws_apigatewayv2_api.bypass.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri    = aws_lb_listener.internal.arn
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.bypass.id
}

resource "aws_apigatewayv2_route" "bypass_any" {
  api_id    = aws_apigatewayv2_api.bypass.id
  route_key = "ANY /bypass/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.bypass_alb.id}"
}

resource "aws_apigatewayv2_stage" "bypass" {
  api_id      = aws_apigatewayv2_api.bypass.id
  name        = "$default"
  auto_deploy = true
}
