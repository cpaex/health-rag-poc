# Module: data_aurora  (SPEC.md §5, §4)
#
# Provisions:
#   - Aurora Serverless v2 PostgreSQL cluster (RDS Data API enabled)
#   - RDS-managed master credential in Secrets Manager
#   - pgvector / pg_trgm extensions + the §4 schema, bootstrapped via a
#     null_resource that runs scripts/apply_sql.py over the RDS Data API
#     (no Lambda / no in-VPC connectivity required)
#
# ── Build-time verification (2026-09-01) ──────────────────────────────────────
#   * pgvector 0.8.0 requires Aurora PostgreSQL 16.8 / 15.12 / 14.17 / 13.20 or
#     higher (AWS "Announcing pgvector 0.8.0 support in Aurora PostgreSQL",
#     2025-04). engine_version is pinned to 16.8 as the floor; bump to the latest
#     16.x patch available in the target region before apply.
#   * RDS Data API (redesigned) is supported on Aurora Serverless v2 PostgreSQL
#     13.11+ / 14.8+ / 15.3+ (AWS "Amazon Aurora PostgreSQL now supports RDS Data
#     API", 2023-12) — 16.8 is well within range.
#   * "Aurora Serverless v2" was marketing-renamed "Aurora serverless" in 2026-04;
#     the Terraform shape is unchanged: engine_mode omitted (defaults to
#     provisioned) + serverlessv2_scaling_configuration + db.serverless instances.
# ─────────────────────────────────────────────────────────────────────────────

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

variable "db_subnet_group_name" {
  type = string
}

variable "vpc_security_group_ids" {
  type = list(string)
}

variable "engine_version" {
  type        = string
  default     = "16.8"
  description = "Aurora PostgreSQL engine version — floor for pgvector 0.8.0; verify latest 16.x before apply"
}

variable "database_name" {
  type    = string
  default = "clinical_rag"
}

variable "master_username" {
  type    = string
  default = "clinical_rag_admin"
}

variable "min_capacity" {
  type        = number
  default     = 0.5
  description = "Serverless v2 min ACUs. Set to 0 (with seconds_until_auto_pause) for scale-to-zero; kept at 0.5 in dev so KB smoke tests don't hit cold starts."
}

variable "max_capacity" {
  type    = number
  default = 2
}

variable "schema_sql_path" {
  type        = string
  default     = ""
  description = "Path to the §4 migration SQL. Defaults to this module's sql/001_init.sql."
}

locals {
  schema_sql_path = var.schema_sql_path != "" ? var.schema_sql_path : "${path.module}/sql/001_init.sql"
}

resource "aws_rds_cluster" "this" {
  cluster_identifier = "${var.name_prefix}-aurora"
  engine             = "aurora-postgresql"
  engine_version     = var.engine_version
  database_name      = var.database_name

  master_username             = var.master_username
  manage_master_user_password = true # RDS creates + rotates the secret in Secrets Manager

  db_subnet_group_name   = var.db_subnet_group_name
  vpc_security_group_ids = var.vpc_security_group_ids
  storage_encrypted      = true
  enable_http_endpoint   = true # RDS Data API
  apply_immediately      = true
  skip_final_snapshot    = true  # dev only
  deletion_protection    = false # dev only

  serverlessv2_scaling_configuration {
    min_capacity = var.min_capacity
    max_capacity = var.max_capacity
  }
}

resource "aws_rds_cluster_instance" "this" {
  identifier         = "${var.name_prefix}-aurora-1"
  cluster_identifier = aws_rds_cluster.this.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version
}

# ── §4 schema bootstrap over the RDS Data API ────────────────────────────────
# Runs at apply time only. Re-runs when the cluster or the SQL file changes.
# The SQL is idempotent (CREATE ... IF NOT EXISTS), so re-runs are safe.
resource "null_resource" "schema_bootstrap" {
  triggers = {
    cluster_arn = aws_rds_cluster.this.arn
    sql_sha     = filesha256(local.schema_sql_path)
    script_sha  = filesha256("${path.module}/../../../scripts/apply_sql.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 "${path.module}/../../../scripts/apply_sql.py" \
        --resource-arn "${aws_rds_cluster.this.arn}" \
        --secret-arn "${aws_rds_cluster.this.master_user_secret[0].secret_arn}" \
        --database "${var.database_name}" \
        --file "${local.schema_sql_path}"
    EOT
  }

  depends_on = [aws_rds_cluster_instance.this]
}

output "cluster_arn" {
  value       = aws_rds_cluster.this.arn
  description = "-> AURORA_CLUSTER_ARN"
}

output "cluster_id" {
  value = aws_rds_cluster.this.id
}

output "secret_arn" {
  value       = aws_rds_cluster.this.master_user_secret[0].secret_arn
  description = "-> AURORA_SECRET_ARN (RDS-managed master credential)"
}

output "database_name" {
  value = var.database_name
}

output "endpoint" {
  value = aws_rds_cluster.this.endpoint
}

output "reader_endpoint" {
  value = aws_rds_cluster.this.reader_endpoint
}
