#!/usr/bin/env sh
set -eu

BUCKET_NAME="mygamelist-uploads"

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if awslocal s3api list-buckets >/dev/null 2>&1; then
    break
  fi
  echo "Waiting for LocalStack S3 to be ready... attempt $attempt"
  sleep 1
done

if ! awslocal s3api head-bucket --bucket "$BUCKET_NAME" >/dev/null 2>&1; then
  awslocal s3api create-bucket --bucket "$BUCKET_NAME" >/dev/null
fi

awslocal s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true >/dev/null

echo "S3 bucket '$BUCKET_NAME' is ready."
