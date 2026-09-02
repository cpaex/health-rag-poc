# Module: agentcore  (SPEC.md §5, §12 Phase 6)
# Provisions:
#   - aws_bedrockagentcore_agent_runtime
#   - aws_bedrockagentcore_gateway
#   - aws_bedrockagentcore_memory
#   - associated IAM execution role
#
# BEFORE HAND-WRITING THIS MODULE (SPEC.md §5): run
#   agentcore create --template production --iac terraform
# in a scratch dir and use its generated Terraform as the reference for
# agent_runtime / gateway / memory resource config.
#
# VERIFY AT BUILD TIME: resource names + argument schema against
#   https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime
# Agent Runtime requires ARM64-compatible packaging — confirm build target.
#
# Phase 6: implement.

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

variable "runtime_image_uri" {
  type    = string
  default = null
}

output "agent_runtime_arn" {
  value       = null
  description = "Phase 6 -> AGENTCORE_RUNTIME_ARN"
}

output "gateway_arn" {
  value       = null
  description = "Phase 6"
}

output "memory_arn" {
  value       = null
  description = "Phase 6"
}
