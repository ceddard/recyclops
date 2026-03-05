# Relatórios de acessibilidade
resource "aws_dynamodb_table" "reports" {
  name         = "${var.project_name}-reports"
  billing_mode = "PAY_PER_REQUEST" # on-demand, grátis em baixo volume
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # TTL: remove reports com +90 dias automaticamente
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# Regras de bypass
resource "aws_dynamodb_table" "bypass_rules" {
  name         = "${var.project_name}-bypass-rules"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
