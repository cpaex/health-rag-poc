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
