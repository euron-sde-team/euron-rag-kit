variable "name_prefix" {
  description = "Prefix for every resource name. Queues are <name_prefix>-jobs and <name_prefix>-jobs-dlq."
  type        = string
}

variable "kms_key_arn" {
  description = "CMK for server-side encryption. Null uses SQS-managed encryption."
  type        = string
  default     = null
}

variable "visibility_timeout_seconds" {
  description = "How long a received message stays hidden; must match the worker's VISIBILITY_S."
  type        = number
  default     = 300
}

variable "message_retention_seconds" {
  description = "How long an unprocessed message is kept (4 days by default)."
  type        = number
  default     = 345600
}

variable "max_receive_count" {
  description = "Receives before a message moves to the dead-letter queue."
  type        = number
  default     = 3
}
