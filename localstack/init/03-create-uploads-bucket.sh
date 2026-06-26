#!/usr/bin/env sh
set -eu

BUCKET_NAME="mygamelist-uploads"

if awslocal s3api head-bucket --bucket "$BUCKET_NAME" >/dev/null 2>&1; then
  echo "S3 bucket '$BUCKET_NAME' is ready."
  exit 0
fi

awslocal s3api create-bucket --bucket "$BUCKET_NAME" >/dev/null
awslocal s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true >/dev/null

echo "S3 bucket '$BUCKET_NAME' is ready."
