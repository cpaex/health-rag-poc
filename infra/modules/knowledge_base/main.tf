# Module: knowledge_base  (SPEC.md §5)
# Provisions: Bedrock Knowledge Base pointed at the Aurora cluster, hybrid search
# enabled, S3 data source for raw notes.
#
# VERIFY AT BUILD TIME (SPEC.md §5): exact Terraform resource name in the AWS
# provider docs. Knowledge Bases live under the `bedrockagent` service namespace
# (NOT `bedrockagentcore`). Candidate resources to confirm:
#   - aws_bedrockagent_knowledge_base
#   - aws_bedrockagent_data_source
# Confirm RDS/Aurora storage_configuration schema + HYBRID search field names.
#
# Phase 2: implement + smoke-test the Retrieve API.

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

variable "aurora_cluster_arn" {
  type    = string
  default = null
}

variable "aurora_secret_arn" {
  type    = string
  default = null
}

variable "embedding_model_arn" {
  type    = string
  default = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
}

variable "raw_notes_bucket_arn" {
  type    = string
  default = null
}

output "knowledge_base_id" {
  value       = null
  description = "Phase 2 -> KNOWLEDGE_BASE_ID"
}

output "data_source_id" {
  value       = null
  description = "Phase 2"
}
