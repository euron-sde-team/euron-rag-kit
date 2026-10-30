output "queue_url" {
  description = "SQS_QUEUE_URL for the API and the worker."
  value       = aws_sqs_queue.jobs.url
}

output "queue_arn" {
  description = "Jobs queue ARN, for IAM policies."
  value       = aws_sqs_queue.jobs.arn
}

output "queue_name" {
  description = "Jobs queue name, for CloudWatch alarms."
  value       = aws_sqs_queue.jobs.name
}

output "dlq_url" {
  description = "Dead-letter queue URL."
  value       = aws_sqs_queue.dlq.url
}

output "dlq_name" {
  description = "Dead-letter queue name, for CloudWatch alarms."
  value       = aws_sqs_queue.dlq.name
}
