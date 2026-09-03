# Populated per phase. Consumed by scripts/deploy.sh to write .env /
# agent/harness_config.yaml.

# ── Phase 1 ────────────────────────────────────────────────────────────────
output "aws_region" {
  value = var.aws_region
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "aurora_cluster_arn" {
  value = module.data_aurora.cluster_arn
}

output "aurora_secret_arn" {
  value = module.data_aurora.secret_arn
}

output "aurora_database_name" {
  value = module.data_aurora.database_name
}

output "aurora_endpoint" {
  value = module.data_aurora.endpoint
}

output "raw_notes_bucket" {
  value = module.ingestion.raw_notes_bucket
}

output "seed_fhir_bucket" {
  value = module.ingestion.seed_fhir_bucket
}

output "ingestion_role_arn" {
  value = module.ingestion.ingestion_role_arn
}

# ── Phase 2 ────────────────────────────────────────────────────────────────
output "knowledge_base_id" {
  value = module.knowledge_base.knowledge_base_id
}

output "knowledge_base_data_source_id" {
  value = module.knowledge_base.data_source_id
}

# ── Phase 5 ────────────────────────────────────────────────────────────────
output "bedrock_guardrail_id" {
  value = module.guardrails.guardrail_id
}

output "bedrock_guardrail_version" {
  value = module.guardrails.guardrail_version
}

# ── Phase 6 ────────────────────────────────────────────────────────────────
output "agentcore_runtime_arn" {
  value = module.agentcore.agent_runtime_arn
}

output "agentcore_runtime_id" {
  value = module.agentcore.agent_runtime_id
}

output "agentcore_ecr_repository_url" {
  value = module.agentcore.ecr_repository_url
}

output "agentcore_memory_id" {
  value = module.agentcore.memory_id
}
