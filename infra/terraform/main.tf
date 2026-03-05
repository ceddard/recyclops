terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "recyclops-terraform-state"
    key            = "recyclops/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "recyclops-terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "recyclops"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
