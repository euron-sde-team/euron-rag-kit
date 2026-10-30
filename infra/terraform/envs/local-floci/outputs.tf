output "corpus_bucket" {
  description = "S3_BUCKET for the local stack."
  value       = module.storage.bucket_name
}

output "kms_key_alias" {
  description = "S3_KMS_KEY_ID for the local stack."
  value       = module.kms.alias_name
}

output "jobs_queue_url" {
  description = "SQS_QUEUE_URL for the local stack."
  value       = module.queue.queue_url
}

output "jobs_dlq_url" {
  description = "Dead-letter queue for jobs that failed repeatedly."
  value       = module.queue.dlq_url
}
