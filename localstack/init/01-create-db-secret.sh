#!/usr/bin/env sh
set -eu

create_or_update_secret() {
  name="$1"
  value="$2"

  if awslocal secretsmanager describe-secret --secret-id "$name" >/dev/null 2>&1; then
    awslocal secretsmanager put-secret-value --secret-id "$name" --secret-string "$value" >/dev/null
  else
    awslocal secretsmanager create-secret --name "$name" --secret-string "$value" >/dev/null
  fi
}

create_or_update_secret "mygamelist/db" '{
  "sqlalchemy_url": "postgresql+psycopg://mygamelist:mygamelist@localhost:5432/mygamelist",
  "url": "jdbc:postgresql://localhost:5432/mygamelist",
  "username": "mygamelist",
  "password": "mygamelist"
}'

create_or_update_secret "mygamelist/db-docker" '{
  "sqlalchemy_url": "postgresql+psycopg://mygamelist:mygamelist@postgres:5432/mygamelist",
  "url": "jdbc:postgresql://postgres:5432/mygamelist",
  "username": "mygamelist",
  "password": "mygamelist"
}'

echo "Secret 'mygamelist/db' is ready."
echo "Secret 'mygamelist/db-docker' is ready."
