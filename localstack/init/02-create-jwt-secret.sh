#!/usr/bin/env sh
set -eu

SECRET_NAME="mygamelist/jwt"
SECRET_VALUE='{"secret":"localstack-dev-jwt-secret-change-before-production-64-bytes"}'

if awslocal secretsmanager describe-secret --secret-id "$SECRET_NAME" >/dev/null 2>&1; then
  awslocal secretsmanager put-secret-value --secret-id "$SECRET_NAME" --secret-string "$SECRET_VALUE" >/dev/null
else
  awslocal secretsmanager create-secret --name "$SECRET_NAME" --secret-string "$SECRET_VALUE" >/dev/null
fi

echo "Secret 'mygamelist/jwt' is ready."
