terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # SPEC.md §1: AgentCore resources supported in hashicorp/aws v6.51+.
      # VERIFY AT BUILD TIME: bump to the current release and confirm
      # aws_bedrockagentcore_* / aws_bedrockagent_knowledge_base / aws_bedrock_guardrail
      # resource names and schemas.
      version = ">= 6.51"
    }
  }

  # Phase 1: configure a remote backend (S3 + DynamoDB lock) before first apply.
  # backend "s3" {}
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = {
      Project     = "clinical-agentic-rag"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}
