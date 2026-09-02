# dev environment composition (SPEC.md §5).
#
# Modules are enabled phase by phase. Keep `terraform plan` clean at every step.
#   Phase 1 (ACTIVE): network, data_aurora, ingestion
#   Phase 2:          knowledge_base
#   Phase 5:          guardrails
#   Phase 6:          agentcore, observability

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
# module "knowledge_base" {
#   source               = "../../modules/knowledge_base"
#   name_prefix          = var.name_prefix
#   aurora_cluster_arn   = module.data_aurora.cluster_arn
#   aurora_secret_arn    = module.data_aurora.secret_arn
#   raw_notes_bucket_arn = module.ingestion.raw_notes_bucket_arn
# }

# ---------------------------------------------------------------------------
# Phase 5 — Guardrails
# ---------------------------------------------------------------------------
# module "guardrails" {
#   source      = "../../modules/guardrails"
#   name_prefix = var.name_prefix
# }

# ---------------------------------------------------------------------------
# Phase 6 — AgentCore + observability
# ---------------------------------------------------------------------------
# module "agentcore" {
#   source      = "../../modules/agentcore"
#   name_prefix = var.name_prefix
# }
#
# module "observability" {
#   source      = "../../modules/observability"
#   name_prefix = var.name_prefix
# }
