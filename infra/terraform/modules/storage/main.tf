# One private bucket for every original file uploaded to RAGKit. Nothing is ever public:
# the API checks project membership and streams the bytes itself, so the bucket needs
# no CORS and no presigned-URL exposure.
resource "aws_s3_bucket" "corpus" {
  #checkov:skip=CKV_AWS_144:Cross-region replication is an organisation-level DR decision; enable it per deployment.
  #checkov:skip=CKV_AWS_18:Access logging targets a separate log bucket an operator chooses; CloudTrail data events cover object access (docs/guides/operations.md).
  #checkov:skip=CKV2_AWS_62:No consumer for S3 event notifications.
  #checkov:skip=CKV_AWS_21:Versioning is an input (enable_versioning, on in every AWS environment); off only for the local emulator.
  bucket        = "${var.name_prefix}-corpus"
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_public_access_block" "corpus" {
  bucket                  = aws_s3_bucket.corpus.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Versioning protects uploaded originals from accidental overwrite or delete.
resource "aws_s3_bucket_versioning" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.kms_key_arn != null ? "aws:kms" : "AES256"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = var.kms_key_arn != null
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  # Superseded and deleted versions are kept for a recovery window, then removed.
  # Current versions are never expired: how long originals are kept is the operator's
  # decision, made by deleting them.
  rule {
    id     = "expire-noncurrent"
    status = var.enable_versioning ? "Enabled" : "Disabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_days
    }
  }
}

data "aws_iam_policy_document" "corpus" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.corpus.arn, "${aws_s3_bucket.corpus.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "corpus" {
  count      = var.enforce_tls ? 1 : 0
  bucket     = aws_s3_bucket.corpus.id
  policy     = data.aws_iam_policy_document.corpus.json
  depends_on = [aws_s3_bucket_public_access_block.corpus]
}
