# Module: ingestion  (SPEC.md §5)
#
# Provisions:
#   - S3 buckets: raw notes (KB data source), seed FHIR
#   - IAM role for the ingestion pipeline (deidentify -> ontology_link ->
#     chunk -> embed_and_load), least-privilege:
#       * comprehendmedical: DetectPHI / InferICD10CM / InferSNOMEDCT / InferRxNorm
#         (Comprehend Medical has no resource-level scoping — actions on "*")
#       * s3: read/write scoped to the two bucket ARNs only
#       * bedrock: InvokeModel scoped to the Titan embeddings model (embed_and_load)
#       * rds-data: ExecuteStatement / BatchExecuteStatement scoped to the Aurora
#         cluster + its secret (ontology_index_load, embed_and_load)
#
# The role trusts the account root so local dev can `aws sts assume-role` into it;
# in Phase 6 the AgentCore execution role assumes an equivalent policy instead.

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

variable "titan_embedding_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "aurora_cluster_arn" {
  type        = string
  default     = ""
  description = "Set once data_aurora exists; empty disables the rds-data statement."
}

variable "aurora_secret_arn" {
  type    = string
  default = ""
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  buckets = {
    raw_notes = "${var.name_prefix}-raw-notes-${data.aws_caller_identity.current.account_id}"
    seed_fhir = "${var.name_prefix}-seed-fhir-${data.aws_caller_identity.current.account_id}"
  }
  titan_model_arn = "arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.region}::foundation-model/${var.titan_embedding_model_id}"
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets
  bucket   = each.value
  tags     = { Name = each.value }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each                = aws_s3_bucket.this
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  rule {
    # SSE-S3 (not SSE-KMS): the AWS-managed aws/s3 key has a fixed key policy that
    # can't grant the Bedrock KB service role kms:Decrypt, which would block
    # Phase 2 ingestion. Swap to a customer-managed KMS key + key policy if
    # encryption-at-rest with a controlled key becomes a requirement.
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ── Ingestion pipeline role ─────────────────────────────────────────────────
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_iam_role" "ingestion" {
  name               = "${var.name_prefix}-ingestion"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "ingestion" {
  statement {
    sid = "ComprehendMedical"
    actions = [
      "comprehendmedical:DetectPHI",
      "comprehendmedical:InferICD10CM",
      "comprehendmedical:InferSNOMEDCT",
      "comprehendmedical:InferRxNorm",
    ]
    resources = ["*"] # Comprehend Medical does not support resource-level permissions
  }

  statement {
    sid       = "S3ObjectAccess"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [for b in aws_s3_bucket.this : "${b.arn}/*"]
  }

  statement {
    sid       = "S3ListBuckets"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [for b in aws_s3_bucket.this : b.arn]
  }

  statement {
    sid       = "BedrockTitanEmbeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.titan_model_arn]
  }

  dynamic "statement" {
    for_each = var.aurora_cluster_arn != "" ? [1] : []
    content {
      sid = "RdsDataApi"
      actions = [
        "rds-data:ExecuteStatement",
        "rds-data:BatchExecuteStatement",
      ]
      resources = [var.aurora_cluster_arn]
    }
  }

  dynamic "statement" {
    for_each = var.aurora_secret_arn != "" ? [1] : []
    content {
      sid       = "AuroraSecretRead"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.aurora_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "ingestion" {
  name   = "${var.name_prefix}-ingestion"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.ingestion.json
}

output "raw_notes_bucket" {
  value = aws_s3_bucket.this["raw_notes"].bucket
}

output "raw_notes_bucket_arn" {
  value = aws_s3_bucket.this["raw_notes"].arn
}

output "seed_fhir_bucket" {
  value = aws_s3_bucket.this["seed_fhir"].bucket
}

output "seed_fhir_bucket_arn" {
  value = aws_s3_bucket.this["seed_fhir"].arn
}

output "ingestion_role_arn" {
  value       = aws_iam_role.ingestion.arn
  description = "Assume for local pipeline runs; also the template for the AgentCore exec role"
}
