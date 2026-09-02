# Module: observability  (SPEC.md §5)
# Provisions: CloudWatch log groups + CloudWatch Transaction Search enablement for
# AgentCore Observability.
#
# NOTE (SPEC.md §5): a one-time account-level setup step may be required outside
# Terraform (Transaction Search / X-Ray trace ingestion enablement). Document the
# exact manual step in this module's README once confirmed in Phase 6.
#
# Phase 6: implement aws_cloudwatch_log_group(s); wire Transaction Search.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.51"
    }
  }
}

variable "name_prefix" {
  type    = string
  default = "clinical-rag-dev"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

output "log_group_names" {
  value       = []
  description = "Phase 6"
}
