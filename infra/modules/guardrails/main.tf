# Module: guardrails  (SPEC.md §5, §7)
# Provisions: Bedrock Guardrail resource with:
#   - Sensitive-info filters: built-in PII (names, SSNs, addresses, phone numbers)
#     + custom regex for the seed data's MRN format
#   - Denied topics: definitive diagnosis statements; treatment directives phrased
#     as instructions rather than decision support
#   - Prompt-attack protection: enabled
#
# VERIFY AT BUILD TIME (SPEC.md §5): resource name — likely aws_bedrock_guardrail
# under the `bedrock` service namespace. Confirm regex/topic/PII block schema.
#
# Phase 5: implement. Applied on BOTH input and output at the final model
# invocation in agent/supervisor.py.

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

variable "mrn_regex" {
  type        = string
  default     = "MRN-[0-9]{7}"
  description = "Seed data MRN format — keep in sync with ingestion/seed_data"
}

output "guardrail_id" {
  value       = null
  description = "Phase 5 -> BEDROCK_GUARDRAIL_ID"
}

output "guardrail_version" {
  value       = null
  description = "Phase 5 -> BEDROCK_GUARDRAIL_VERSION"
}
