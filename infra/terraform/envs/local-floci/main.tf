# -----------------------------------------------------------------------------
# Local environment on the Floci AWS emulator.
#
# The modules that build AWS run here unchanged; only the provider endpoints differ.
# `make up` applies this automatically (the compose `terraform` one-shot) before the API
# and the worker start, so local development stores files in S3 with SSE-KMS and
# runs its jobs through SQS with a dead-letter queue, exactly as on AWS. By hand, against a
# running emulator:
#
#   terraform -chdir=infra/terraform/envs/local-floci init
#   terraform -chdir=infra/terraform/envs/local-floci apply
# -----------------------------------------------------------------------------

module "kms" {
  source                  = "../../modules/kms"
  name_prefix             = var.name_prefix
  deletion_window_in_days = 7
}

module "storage" {
  source            = "../../modules/storage"
  name_prefix       = var.name_prefix
  kms_key_arn       = module.kms.key_arn
  enforce_tls       = false # the emulator speaks plain HTTP
  enable_versioning = false
  force_destroy     = true
}

module "queue" {
  source      = "../../modules/queue"
  name_prefix = var.name_prefix
  kms_key_arn = module.kms.key_arn
}

# Generated secrets are an AWS-deployment concern; locally compose reads
# deploy/compose/.env (make env). Created here anyway so the module is exercised.
module "secrets" {
  source                  = "../../modules/secrets"
  name_prefix             = var.name_prefix
  kms_key_arn             = module.kms.key_arn
  recovery_window_in_days = 0
}
