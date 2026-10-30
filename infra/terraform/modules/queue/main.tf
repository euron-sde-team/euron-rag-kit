# The jobs queue: one message per unit of work (parse a document, index it into one
# pipeline version's index, run an evaluation), consumed by the worker.
#
# A message that fails processing becomes visible again after its timeout and is retried;
# after max_receive_count receives SQS moves it to the dead-letter queue, where it waits
# for an operator to inspect and redrive it. The worker extends visibility while a job
# runs, so the timeout only bounds how long a crashed worker holds a message.
locals {
  managed_sse = var.kms_key_arn == null
}

resource "aws_sqs_queue" "dlq" {
  name                              = "${var.name_prefix}-jobs-dlq"
  message_retention_seconds         = 1209600
  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = local.managed_sse ? null : 300
  sqs_managed_sse_enabled           = local.managed_sse ? true : null
}

resource "aws_sqs_queue" "jobs" {
  name                              = "${var.name_prefix}-jobs"
  visibility_timeout_seconds        = var.visibility_timeout_seconds
  message_retention_seconds         = var.message_retention_seconds
  receive_wait_time_seconds         = 20
  kms_master_key_id                 = var.kms_key_arn
  kms_data_key_reuse_period_seconds = local.managed_sse ? null : 300
  sqs_managed_sse_enabled           = local.managed_sse ? true : null
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.jobs.arn]
  })
}
