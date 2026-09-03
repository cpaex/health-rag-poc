# Module: guardrails  (SPEC.md §5, §7)
#
# Bedrock Guardrail applied on BOTH input and output of the supervisor's final
# model call (wired in agent/supervisor.py via bedrock-runtime:ApplyGuardrail).
#
# ── Build-time verification (2026-09-02, hashicorp/aws v6.62 schema) ─────────
#   Resource: aws_bedrock_guardrail  ✔ (under the `bedrock` namespace, as SPEC
#   §5 guessed). Required: name, blocked_input_messaging, blocked_outputs_messaging.
#   - PROMPT_ATTACK filter: output_strength must be "NONE" (the filter only
#     applies to input); input_strength carries the setting.
#   - PII types use Bedrock's managed identifiers (NAME, PHONE, ADDRESS,
#     US_SOCIAL_SECURITY_NUMBER, EMAIL).
# ───────────────────────────────────────────────────────────────────────────

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

variable "pii_action" {
  type        = string
  default     = "ANONYMIZE"
  description = "BLOCK or ANONYMIZE for detected built-in PII entities"
}

resource "aws_bedrock_guardrail" "this" {
  name                      = "${var.name_prefix}-guardrail"
  description               = "Clinical RAG: sensitive-info + denied-topics + prompt-attack"
  blocked_input_messaging   = "This request can't be processed as phrased. Rephrase it as a decision-support question about the authorized patient."
  blocked_outputs_messaging = "The generated answer was withheld by a safety policy. Ask for cited decision-support information instead."

  # --- Prompt-attack protection (input only) ---
  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  # --- Sensitive information: built-in PII + MRN regex ---
  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = toset(["NAME", "PHONE", "ADDRESS", "US_SOCIAL_SECURITY_NUMBER", "EMAIL"])
      content {
        type   = pii_entities_config.value
        action = var.pii_action
      }
    }

    regexes_config {
      name        = "mrn"
      description = "Seed data medical record number"
      pattern     = var.mrn_regex
      action      = "ANONYMIZE"
    }
  }

  # --- Denied topics (SPEC §7) ---
  topic_policy_config {
    topics_config {
      name       = "definitive_diagnosis"
      type       = "DENY"
      definition = "Statements that assert a definitive medical diagnosis for the patient as established fact, rather than framing findings as decision support for a clinician to weigh."
      examples = [
        "The patient definitely has sepsis.",
        "This confirms the patient has cancer.",
      ]
    }

    topics_config {
      name       = "treatment_directive"
      type       = "DENY"
      definition = "Treatment or medication instructions phrased as a directive/command to act (start, stop, prescribe, administer a dose) rather than as options and evidence for a clinician to consider."
      examples = [
        "Start the patient on 40 mg furosemide twice daily now.",
        "Discontinue the anticoagulant immediately.",
      ]
    }
  }
}

output "guardrail_id" {
  value       = aws_bedrock_guardrail.this.guardrail_id
  description = "-> BEDROCK_GUARDRAIL_ID"
}

output "guardrail_arn" {
  value = aws_bedrock_guardrail.this.guardrail_arn
}

output "guardrail_version" {
  value       = aws_bedrock_guardrail.this.version
  description = "-> BEDROCK_GUARDRAIL_VERSION (the DRAFT working version)"
}
