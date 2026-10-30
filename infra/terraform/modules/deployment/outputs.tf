output "urls" {
  description = "Public URLs of the web app and the API."
  value       = local.urls
}

output "ecr_repository_urls" {
  description = "Image repositories, for docker push."
  value       = module.ecr.repository_urls
}

output "cluster_name" {
  description = "ECS cluster."
  value       = aws_ecs_cluster.this.name
}

output "service_names" {
  description = "ECS service names."
  value       = { api = module.api.service_name, worker = module.worker.service_name, web = module.web.service_name }
}

output "cli_task_definition" {
  description = "Task definition family for one-off CLI tasks (make aws-cli)."
  value       = module.cli.task_definition_family
}

output "cli_security_group_id" {
  description = "Security group for one-off CLI tasks."
  value       = module.cli.security_group_id
}

output "private_subnet_ids" {
  description = "Private subnets, for one-off tasks."
  value       = module.network.private_subnet_ids
}

output "corpus_bucket" {
  description = "Bucket holding the original files."
  value       = module.storage.bucket_name
}

output "jobs_queue_url" {
  description = "Jobs queue: parse, index and evaluation work."
  value       = module.queue.queue_url
}

output "jobs_dlq_url" {
  description = "Dead-letter queue for jobs that failed repeatedly."
  value       = module.queue.dlq_url
}

output "database_address" {
  description = "RDS endpoint (private)."
  value       = module.database.address
}

output "load_balancer_dns_name" {
  description = "Point app.<domain> and api.<domain> here when the zone is not in Route53."
  value       = module.edge.dns_name
}

output "certificate_validation_records" {
  description = "DNS records to publish when the zone is not in Route53."
  value       = module.edge.certificate_validation_records
}

output "dashboard_name" {
  description = "CloudWatch dashboard."
  value       = module.observability.dashboard_name
}
