variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = ""
}

variable "name_prefix" {
  type    = string
  default = "clinical-rag-dev"
}

variable "titan_embedding_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "rerank_model_arn" {
  type    = string
  default = "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0"
}

variable "mock_fhir_endpoint_url" {
  type        = string
  default     = ""
  description = "Reachable FHIR endpoint for the deployed runtime (the local mock is not reachable from AgentCore)."
}

variable "enable_transaction_search" {
  type        = bool
  default     = false
  description = "Account/region-wide CloudWatch Transaction Search for AgentCore Observability."
}
