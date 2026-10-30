variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
  default     = "ragkit-dev"
}

variable "domain" {
  description = "Parent domain: the app is served at app.<domain> and the API at api.<domain>."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone for the domain. Null: publish the DNS records from the outputs yourself."
  type        = string
  default     = null
}

variable "certificate_arn" {
  description = "Existing ACM certificate for app.<domain> and api.<domain>. Null requests one."
  type        = string
  default     = null
}

variable "product_name" {
  description = "Name shown in the web app."
  type        = string
  default     = "Euron RAGKit"
}

variable "image_tag" {
  description = "Image tag to deploy (make aws-deploy passes the git commit)."
  type        = string
  default     = "latest"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "cache_node_type" {
  description = "ElastiCache node type."
  type        = string
  default     = "cache.t4g.small"
}

variable "alarm_email" {
  description = "Address that receives alarm notifications."
  type        = string
  default     = null
}

variable "llm_provider" {
  description = "none (offline extractive answers), openai (OpenAI-compatible) or ollama."
  type        = string
  default     = "none"
}

variable "llm_model" {
  description = "Model name for llm_provider."
  type        = string
  default     = ""
}

variable "llm_base_url" {
  description = "OpenAI-compatible endpoint."
  type        = string
  default     = "https://api.openai.com/v1"
}

variable "llm_api_key_secret_arn" {
  description = "ECS valueFrom reference to the provider key (<secret arn>:<json key>::)."
  type        = string
  default     = null
}
