# Module: agentcore  (SPEC.md §5, §12 Phase 6)
#
# Provisions the AgentCore runtime for the supervisor:
#   - ECR repo + an ARM64 container build/push (null_resource) — Agent Runtime
#     requires linux/arm64 packaging
#   - aws_bedrockagentcore_agent_runtime (container artifact) + a "DEV" endpoint
#   - aws_bedrockagentcore_memory (+ optional SEMANTIC long-term strategy)
#   - aws_bedrockagentcore_gateway (OPTIONAL — the SMART-on-FHIR/JWT extension
#     point; needs a real IdP discovery URL, so off by default)
#   - the runtime execution IAM role (AWS runtime-permissions baseline + this
#     app's KB / Aurora / Guardrail / Rerank access)
#
# ── Build-time verification (2026-09-03) ────────────────────────────────────
#   * SPEC §5 says run `agentcore create --template production --iac terraform`
#     first. The current CLI form is:
#         agentcore create -p <name> -t production --iac Terraform \
#           --agent-framework Strands --model-provider Bedrock --non-interactive
#     (`--template`→`-t`, `--iac terraform`→`--iac Terraform`, value is
#     case-sensitive). The Python `bedrock-agentcore-starter-toolkit` that ships
#     this command is now marked "no longer supported" in favour of the npm
#     `@aws/agentcore` CLI — see the Phase 6 notes in DEPLOY.md. This module is
#     modelled on that toolkit's generated Terraform, trimmed to SPEC §5 scope
#     and pointed at our own image + IAM.
#   * Resource shapes verified against hashicorp/aws v6.62:
#       aws_bedrockagentcore_agent_runtime  — agent_runtime_artifact {
#         container_configuration { container_uri } }, network_configuration {
#         network_mode }, environment_variables, authorizer_configuration {
#         custom_jwt_authorizer { discovery_url, allowed_audience } }
#       aws_bedrockagentcore_memory         — event_expiry_duration (days, int)
#       aws_bedrockagentcore_gateway        — authorizer_type, protocol_type,
#         authorizer_configuration { custom_jwt_authorizer { discovery_url } }
#       aws_bedrockagentcore_agent_runtime_endpoint — agent_runtime_id, name
# ───────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.51"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2"
    }
  }
}

variable "name_prefix" {
  type    = string
  default = "clinical-rag-dev"
}

variable "source_dir" {
  type        = string
  description = "Repo root (contains Dockerfile + agent/) for the ARM64 image build"
}

variable "runtime_environment" {
  type        = map(string)
  default     = {}
  description = "Env vars for the runtime container: KNOWLEDGE_BASE_ID, AURORA_*, BEDROCK_GUARDRAIL_*, RERANK_MODEL_ARN, MOCK_FHIR_ENDPOINT_URL, AGENT_MODE=agentcore"
}

variable "knowledge_base_arn" {
  type    = string
  default = "*"
}

variable "aurora_cluster_arn" {
  type    = string
  default = "*"
}

variable "aurora_secret_arn" {
  type    = string
  default = "*"
}

variable "guardrail_arn" {
  type    = string
  default = "*"
}

variable "memory_event_expiry_days" {
  type    = number
  default = 30
}

variable "enable_long_term_memory" {
  type        = bool
  default     = true
  description = "Add a SEMANTIC long-term memory strategy (uses AgentCore's default extraction models)"
}

variable "jwt_discovery_url" {
  type        = string
  default     = ""
  description = "OIDC discovery URL for inbound JWT auth (real Cognito/Entra). Empty = no inbound authorizer (dev)."
}

variable "jwt_allowed_audience" {
  type    = list(string)
  default = []
}

variable "create_gateway" {
  type        = bool
  default     = false
  description = "Create an AgentCore Gateway with a JWT authorizer. Needs jwt_discovery_url."
}

variable "region" {
  type    = string
  default = null
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  app         = replace(title(replace(var.name_prefix, "-", " ")), " ", "")
  image_tag   = "latest"
  arn_prefix  = "arn:${data.aws_partition.current.partition}"
  region_name = coalesce(var.region, data.aws_region.current.region)
  account_id  = data.aws_caller_identity.current.account_id
  use_jwt     = var.jwt_discovery_url != ""
}

# ── ECR + ARM64 image ──────────────────────────────────────────────────────
resource "aws_ecr_repository" "runtime" {
  name                 = "bedrock-agentcore/${lower(var.name_prefix)}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # dev

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "null_resource" "image" {
  triggers = {
    # rebuild when the entrypoint, agent code, or Dockerfile changes
    src_hash    = sha256(join("", [for f in fileset(var.source_dir, "agent/**") : filesha256("${var.source_dir}/${f}")]))
    docker_hash = filesha256("${var.source_dir}/Dockerfile")
    repo_url    = aws_ecr_repository.runtime.repository_url
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      cd "${var.source_dir}"
      aws ecr get-login-password --region ${local.region_name} \
        | docker login --username AWS --password-stdin ${local.account_id}.dkr.ecr.${local.region_name}.amazonaws.com
      # Agent Runtime requires linux/arm64.
      docker buildx build --platform linux/arm64 --provenance=false \
        -t ${aws_ecr_repository.runtime.repository_url}:${local.image_tag} --push .
    EOT
  }
}

# ── Runtime execution role ─────────────────────────────────────────────────
data "aws_iam_policy_document" "runtime_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["${local.arn_prefix}:bedrock-agentcore:${local.region_name}:${local.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "runtime" {
  name               = "${var.name_prefix}-agentcore-runtime"
  assume_role_policy = data.aws_iam_policy_document.runtime_assume.json
}

data "aws_iam_policy_document" "runtime" {
  # --- AWS runtime-permissions baseline ---
  statement {
    sid       = "EcrImage"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.runtime.arn]
  }
  statement {
    sid       = "EcrToken"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
      "logs:DescribeLogStreams", "logs:DescribeLogGroups",
    ]
    resources = [
      "${local.arn_prefix}:logs:${local.region_name}:${local.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*",
      "${local.arn_prefix}:logs:${local.region_name}:${local.account_id}:log-group:*",
    ]
  }
  statement {
    sid       = "XRay"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"]
    resources = ["*"]
  }
  statement {
    sid       = "CloudWatchMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }
  statement {
    sid = "WorkloadIdentity"
    actions = [
      "bedrock-agentcore:GetWorkloadAccessToken",
      "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
      "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
    ]
    resources = [
      "${local.arn_prefix}:bedrock-agentcore:${local.region_name}:${local.account_id}:workload-identity-directory/default",
      "${local.arn_prefix}:bedrock-agentcore:${local.region_name}:${local.account_id}:workload-identity-directory/default/workload-identity/*",
    ]
  }

  # --- This app's data-plane access ---
  statement {
    sid       = "BedrockInvokeAndRerank"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Rerank"]
    resources = ["${local.arn_prefix}:bedrock:*::foundation-model/*", "${local.arn_prefix}:bedrock:${local.region_name}:${local.account_id}:*"]
  }
  statement {
    sid       = "KnowledgeBaseRetrieve"
    actions   = ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"]
    resources = [var.knowledge_base_arn]
  }
  statement {
    sid       = "ApplyGuardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [var.guardrail_arn]
  }
  statement {
    sid       = "AuroraDataApi"
    actions   = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"]
    resources = [var.aurora_cluster_arn]
  }
  statement {
    sid       = "AuroraSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.aurora_secret_arn]
  }
}

resource "aws_iam_role_policy" "runtime" {
  name   = "${var.name_prefix}-agentcore-runtime"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.runtime.json
}

# ── Memory ─────────────────────────────────────────────────────────────────
resource "aws_bedrockagentcore_memory" "this" {
  name                  = "${local.app}Memory"
  description           = "Short-term session memory for the clinical RAG supervisor"
  event_expiry_duration = var.memory_event_expiry_days
}

resource "aws_bedrockagentcore_memory_strategy" "semantic" {
  count               = var.enable_long_term_memory ? 1 : 0
  memory_id           = aws_bedrockagentcore_memory.this.id
  name                = "SemanticFacts"
  type                = "SEMANTIC"
  namespace_templates = ["/facts/{actorId}/"]
}

# ── Gateway (optional extension point) ─────────────────────────────────────
data "aws_iam_policy_document" "gateway_assume" {
  count = var.create_gateway ? 1 : 0
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "gateway" {
  count              = var.create_gateway ? 1 : 0
  name               = "${var.name_prefix}-agentcore-gateway"
  assume_role_policy = data.aws_iam_policy_document.gateway_assume[0].json
}

resource "aws_bedrockagentcore_gateway" "this" {
  count           = var.create_gateway ? 1 : 0
  name            = "${local.app}Gateway"
  role_arn        = aws_iam_role.gateway[0].arn
  protocol_type   = "MCP"
  authorizer_type = "CUSTOM_JWT"

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url    = var.jwt_discovery_url
      allowed_audience = var.jwt_allowed_audience
    }
  }
}

# ── Runtime + endpoint ─────────────────────────────────────────────────────
resource "aws_bedrockagentcore_agent_runtime" "this" {
  agent_runtime_name = "${local.app}Supervisor"
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.runtime.repository_url}:${local.image_tag}"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  environment_variables = merge(
    { AWS_REGION = local.region_name, MEMORY_ID = aws_bedrockagentcore_memory.this.id },
    var.runtime_environment,
  )

  dynamic "authorizer_configuration" {
    for_each = local.use_jwt ? [1] : []
    content {
      custom_jwt_authorizer {
        discovery_url    = var.jwt_discovery_url
        allowed_audience = var.jwt_allowed_audience
      }
    }
  }

  depends_on = [null_resource.image, aws_iam_role_policy.runtime]
}

resource "aws_bedrockagentcore_agent_runtime_endpoint" "dev" {
  name             = "DEV"
  agent_runtime_id = aws_bedrockagentcore_agent_runtime.this.agent_runtime_id
}

output "agent_runtime_arn" {
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn
  description = "-> AGENTCORE_RUNTIME_ARN"
}

output "agent_runtime_id" {
  value = aws_bedrockagentcore_agent_runtime.this.agent_runtime_id
}

output "agent_runtime_endpoint_arn" {
  value = aws_bedrockagentcore_agent_runtime_endpoint.dev.agent_runtime_endpoint_arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.runtime.repository_url
}

output "memory_id" {
  value = aws_bedrockagentcore_memory.this.id
}

output "gateway_url" {
  value       = var.create_gateway ? aws_bedrockagentcore_gateway.this[0].gateway_url : null
  description = "MCP gateway URL (null unless create_gateway = true)"
}
