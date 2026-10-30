output "bucket_name" {
  description = "Corpus bucket name (S3_BUCKET)."
  value       = aws_s3_bucket.corpus.bucket
}

output "bucket_arn" {
  description = "Corpus bucket ARN, for IAM policies."
  value       = aws_s3_bucket.corpus.arn
}
