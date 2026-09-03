# Module: observability  (SPEC.md §5)
#
# CloudWatch log groups for the AgentCore runtime/gateway, plus (optionally)
# CloudWatch Transaction Search enablement for AgentCore Observability.
#
# ── Build-time note (2026-09-03) ───────────────────────────────────────────
#   Transaction Search is an ACCOUNT + REGION level setting, not per-resource.
#   It needs two things, both available in hashicorp/aws v6.62:
#     * aws_xray_trace_segment_destination { destination = "CloudWatchLogs" }
#     * aws_xray_indexing_rule (desired_sampling_percentage, default 1; set 100
#       to index all spans)
#   Because it is account-wide and affects X-Ray billing, it is gated behind
#   `enable_transaction_search` (default false) — flip it once, in one env.
#   AgentCore also emits its own logs to /aws/bedrock-agentcore/runtimes/<id>/*
#   which the service creates on first run; the group here is for belt-and-braces
#   retention control + any app-side logging.
# ──────────────────────────────────────────────────────────────────────────

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

variable "enable_transaction_search" {
  type        = bool
  default     = false
  description = "Account/region-wide: send X-Ray segments to CloudWatch Logs + index spans (AgentCore Observability / Transaction Search)."
}

variable "transaction_search_sampling_percent" {
  type    = number
  default = 100
}

resource "aws_cloudwatch_log_group" "runtime" {
  name              = "/clinical-rag/${var.name_prefix}/agentcore-runtime"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/clinical-rag/${var.name_prefix}/agentcore-gateway"
  retention_in_days = var.log_retention_days
}

resource "aws_xray_trace_segment_destination" "cwlogs" {
  count       = var.enable_transaction_search ? 1 : 0
  destination = "CloudWatchLogs"
}

resource "aws_xray_indexing_rule" "spans" {
  count = var.enable_transaction_search ? 1 : 0
  name  = "Default"

  rule {
    probabilistic {
      desired_sampling_percentage = var.transaction_search_sampling_percent
    }
  }

  depends_on = [aws_xray_trace_segment_destination.cwlogs]
}

output "runtime_log_group_name" {
  value = aws_cloudwatch_log_group.runtime.name
}

output "gateway_log_group_name" {
  value = aws_cloudwatch_log_group.gateway.name
}

output "transaction_search_enabled" {
  value = var.enable_transaction_search
}
