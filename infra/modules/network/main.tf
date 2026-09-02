# Module: network  (SPEC.md §5)
# Minimal VPC + 2 private subnets + DB subnet group + security group for Aurora.
# Deliberately small: no IGW/NAT. Aurora is reached via the RDS Data API (an AWS
# API endpoint), not via direct in-VPC TCP, so no outbound routing is needed for
# the v1 pipeline. The security group + private subnets still satisfy Aurora's
# placement requirements and leave room for a future in-VPC client.

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

variable "vpc_cidr" {
  type    = string
  default = "10.60.0.0/16"
}

variable "az_count" {
  type    = number
  default = 2
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_subnet" "private" {
  count             = var.az_count
  vpc_id            = aws_vpc.this.id
  availability_zone = data.aws_availability_zones.available.names[count.index]
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)

  tags = { Name = "${var.name_prefix}-private-${count.index}" }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.name_prefix}-db" }
}

resource "aws_security_group" "aurora" {
  name        = "${var.name_prefix}-aurora"
  description = "Aurora PostgreSQL access (in-VPC clients only)"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "PostgreSQL from within the VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name_prefix}-aurora" }
}

output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "db_subnet_group_name" {
  value = aws_db_subnet_group.this.name
}

output "aurora_security_group_id" {
  value = aws_security_group.aurora.id
}
