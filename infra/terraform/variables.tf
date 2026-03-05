variable "aws_region" {
  description = "Região AWS"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Ambiente (poc, staging, prod)"
  type        = string
  default     = "poc"
}

variable "project_name" {
  type    = string
  default = "recyclops"
}

variable "score_threshold" {
  description = "Score mínimo para aprovar PR (0-100)"
  type        = number
  default     = 50
}

variable "github_webhook_secret" {
  description = "Secret do webhook do GitHub"
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub Personal Access Token (repo + checks)"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true
}

variable "cers_ia_image" {
  description = "Imagem ECR do recyclops-service"
  type        = string
  default     = ""
}

variable "analyzer_image" {
  description = "Imagem ECR do accessibility-analyzer"
  type        = string
  default     = ""
}

variable "bypass_api_image" {
  description = "Imagem ECR do bypass-api"
  type        = string
  default     = ""
}