# Module: knowledge_base  (SPEC.md §5, Phase 2)
#
# Bedrock Knowledge Base (VECTOR type) with an Aurora PostgreSQL / pgvector
# vector store, plus an S3 data source for raw notes and a dedicated service role.
#
# ── Build-time verification (2026-09-01, hashicorp/aws v6.62 schema) ──────────
#   Resource names (SPEC.md §5 asked to verify — "bedrockagent", not
#   "bedrockagentcore"):
#     * aws_bedrockagent_knowledge_base   ✔ exists
#     * aws_bedrockagent_data_source      ✔ exists
#
#   HYBRID SEARCH IS NOT A TERRAFORM SETTING. The KB resource has no
#   hybrid/semantic toggle. For an Aurora pgvector store, hybrid search is:
#     (a) a GIN full-text index on the chunks column  -> created by the §4
#         migration (infra/modules/data_aurora/sql/001_init.sql), and
#     (b) a QUERY-TIME parameter: retrievalConfiguration.vectorSearchConfiguration
#         .overrideSearchType = "HYBRID" on the Retrieve / RetrieveAndGenerate
#         API call -> set by agent/tools/kb_hybrid_retrieve.py and by
#         scripts/kb_smoke_test.py.
#   So "hybrid search enabled" is satisfied by the §4 index + the retrieval
#   tool, not by anything in this module.
#
#   rds_configuration.field_mapping requires primary_key_field / vector_field /
#   text_field / metadata_field; custom_metadata_field is optional and is what
#   enables single-column metadata filtering (our patient_scope filter needs it).
#   Field names below map to the §4 table columns exactly.
#
#   LOAD PATH: SPEC.md §6 step 5 has ingestion/embed_and_load.py write embeddings
#   directly into bedrock_integration.bedrock_kb (self-managed). The S3 data
#   source here is created per SPEC.md §5 but configured with chunking_strategy
#   "NONE" and data_deletion_policy "RETAIN" so a `StartIngestionJob` sync is an
#   optional supplement, not the primary path. If you switch to KB-managed
#   ingestion later, change the chunking strategy and drop embed_and_load.py.
# ─────────────────────────────────────────────────────────────────────────────

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
  type = string
}

variable "aurora_secret_arn" {
  type = string
}

variable "aurora_database_name" {
  type    = string
  default = "clinical_rag"
}

variable "kb_table_name" {
  type        = string
  default     = "bedrock_integration.bedrock_kb"
  description = "Schema-qualified table from the §4 migration"
}

variable "raw_notes_bucket_arn" {
  type = string
}

variable "embedding_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dimensions" {
  type        = number
  default     = 1024
  description = "Must match vector(1024) in the §4 table and the Titan V2 output dim"
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  embedding_model_arn = "arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.region}::foundation-model/${var.embedding_model_id}"
}

# ── KB service role ─────────────────────────────────────────────────────────
data "aws_iam_policy_document" "kb_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "kb" {
  name               = "${var.name_prefix}-kb"
  assume_role_policy = data.aws_iam_policy_document.kb_assume.json
}

data "aws_iam_policy_document" "kb" {
  statement {
    sid       = "InvokeEmbeddingModel"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.embedding_model_arn]
  }

  statement {
    sid       = "DescribeAuroraCluster"
    actions   = ["rds:DescribeDBClusters"]
    resources = [var.aurora_cluster_arn]
  }

  statement {
    sid = "AuroraDataApi"
    actions = [
      "rds-data:ExecuteStatement",
      "rds-data:BatchExecuteStatement",
    ]
    resources = [var.aurora_cluster_arn]
  }

  statement {
    sid       = "ReadAuroraSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.aurora_secret_arn]
  }

  statement {
    sid       = "ReadRawNotesObjects"
    actions   = ["s3:GetObject"]
    resources = ["${var.raw_notes_bucket_arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid       = "ListRawNotesBucket"
    actions   = ["s3:ListBucket"]
    resources = [var.raw_notes_bucket_arn]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role_policy" "kb" {
  name   = "${var.name_prefix}-kb"
  role   = aws_iam_role.kb.id
  policy = data.aws_iam_policy_document.kb.json
}

# ── Knowledge Base ─────────────────────────────────────────────────────────
resource "aws_bedrockagent_knowledge_base" "this" {
  name     = "${var.name_prefix}-kb"
  role_arn = aws_iam_role.kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = local.embedding_model_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.embedding_dimensions
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "RDS"
    rds_configuration {
      resource_arn           = var.aurora_cluster_arn
      credentials_secret_arn = var.aurora_secret_arn
      database_name          = var.aurora_database_name
      table_name             = var.kb_table_name
      field_mapping {
        primary_key_field     = "id"
        vector_field          = "embedding"
        text_field            = "chunks"
        metadata_field        = "metadata"
        custom_metadata_field = "custom_metadata"
      }
    }
  }

  # The §4 migration must have run (pgvector + table + indexes) before Bedrock's
  # create-time preflight check against the Aurora table.
  depends_on = [aws_iam_role_policy.kb]
}

resource "aws_bedrockagent_data_source" "raw_notes" {
  knowledge_base_id   = aws_bedrockagent_knowledge_base.this.id
  name                = "${var.name_prefix}-raw-notes"
  data_deletion_policy = "RETAIN"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = var.raw_notes_bucket_arn
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      # We pre-chunk in ingestion/chunk.py and load via embed_and_load.py.
      chunking_strategy = "NONE"
    }
  }
}

output "knowledge_base_id" {
  value       = aws_bedrockagent_knowledge_base.this.id
  description = "-> KNOWLEDGE_BASE_ID"
}

output "knowledge_base_arn" {
  value = aws_bedrockagent_knowledge_base.this.arn
}

output "data_source_id" {
  value = aws_bedrockagent_data_source.raw_notes.data_source_id
}

output "kb_role_arn" {
  value = aws_iam_role.kb.arn
}
