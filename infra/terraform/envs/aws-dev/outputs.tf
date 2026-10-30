output "urls" {
  description = "Public URLs of the web app and the API."
  value       = module.ragkit.urls
}

output "ecr_repository_urls" {
  description = "Image repositories."
  value       = module.ragkit.ecr_repository_urls
}

output "cluster_name" {
  description = "ECS cluster."
  value       = module.ragkit.cluster_name
}

output "service_names" {
  description = "ECS services."
  value       = module.ragkit.service_names
}

output "cli_task_definition" {
  description = "Task definition for one-off CLI tasks."
  value       = module.ragkit.cli_task_definition
}

output "cli_security_group_id" {
  description = "Security group for one-off CLI tasks."
  value       = module.ragkit.cli_security_group_id
}

output "private_subnet_ids" {
  description = "Private subnets for one-off tasks."
  value       = module.ragkit.private_subnet_ids
}

output "load_balancer_dns_name" {
  description = "Point app.<domain> and api.<domain> here when the zone is not in Route53."
  value       = module.ragkit.load_balancer_dns_name
}

output "certificate_validation_records" {
  description = "DNS records to publish when the zone is not in Route53."
  value       = module.ragkit.certificate_validation_records
}

output "jobs_dlq_url" {
  description = "Dead-letter queue to inspect when job alarms fire."
  value       = module.ragkit.jobs_dlq_url
}
