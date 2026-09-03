# dev environment composition (SPEC.md §5).
#
# Modules are enabled phase by phase. Keep `terraform plan` clean at every step.
#   Phase 1: network, data_aurora, ingestion
#   Phase 2: knowledge_base
#   Phase 5: guardrails
#   Phase 6 (ACTIVE): agentcore, observability

# ---------------------------------------------------------------------------
# Phase 1 — foundation
# ---------------------------------------------------------------------------
module "network" {
  source      = "../../modules/network"
  name_prefix = var.name_prefix
}

module "data_aurora" {
  source = "../../modules/data_aurora"

  name_prefix            = var.name_prefix
  db_subnet_group_name   = module.network.db_subnet_group_name
  vpc_security_group_ids = [module.network.aurora_security_group_id]
}

module "ingestion" {
  source = "../../modules/ingestion"

  name_prefix              = var.name_prefix
  titan_embedding_model_id = var.titan_embedding_model_id
  aurora_cluster_arn       = module.data_aurora.cluster_arn
  aurora_secret_arn        = module.data_aurora.secret_arn
}

# ---------------------------------------------------------------------------
# Phase 2 — Knowledge Base
# ---------------------------------------------------------------------------
module "knowledge_base" {
  source = "../../modules/knowledge_base"

  name_prefix          = var.name_prefix
  aurora_cluster_arn   = module.data_aurora.cluster_arn
  aurora_secret_arn    = module.data_aurora.secret_arn
  aurora_database_name = module.data_aurora.database_name
  raw_notes_bucket_arn = module.ingestion.raw_notes_bucket_arn

  embedding_model_id = var.titan_embedding_model_id

  # Ensure the §4 schema bootstrap (null_resource in data_aurora) completes
  # before Bedrock's create-time preflight against the Aurora table.
  depends_on = [module.data_aurora]
}

# ---------------------------------------------------------------------------
# Phase 5 — Guardrails
# ---------------------------------------------------------------------------
module "guardrails" {
  source      = "../../modules/guardrails"
  name_prefix = var.name_prefix
}

# ---------------------------------------------------------------------------
# Phase 6 — AgentCore + observability
# ---------------------------------------------------------------------------
module "agentcore" {
  source = "../../modules/agentcore"

  name_prefix = var.name_prefix
  source_dir  = abspath("${path.module}/../../..") # repo root: Dockerfile + agent/

  knowledge_base_arn = module.knowledge_base.knowledge_base_arn
  aurora_cluster_arn = module.data_aurora.cluster_arn
  aurora_secret_arn  = module.data_aurora.secret_arn
  guardrail_arn      = module.guardrails.guardrail_arn

  runtime_environment = {
    AGENT_MODE                = "agentcore"
    KNOWLEDGE_BASE_ID         = module.knowledge_base.knowledge_base_id
    AURORA_CLUSTER_ARN        = module.data_aurora.cluster_arn
    AURORA_SECRET_ARN         = module.data_aurora.secret_arn
    AURORA_DATABASE_NAME      = module.data_aurora.database_name
    BEDROCK_GUARDRAIL_ID      = module.guardrails.guardrail_id
    BEDROCK_GUARDRAIL_VERSION = module.guardrails.guardrail_version
    RERANK_MODEL_ARN          = var.rerank_model_arn
    MOCK_FHIR_ENDPOINT_URL    = var.mock_fhir_endpoint_url
  }
}

module "observability" {
  source      = "../../modules/observability"
  name_prefix = var.name_prefix

  # Account/region-wide — enable deliberately, once. See DEPLOY.md §6.
  enable_transaction_search = var.enable_transaction_search
}
