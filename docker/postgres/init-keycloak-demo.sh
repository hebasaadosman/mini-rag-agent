#!/bin/sh
set -eu

# Runs only while a fresh PostgreSQL volume is initialized.  Keycloak receives
# an isolated database and role; it never reuses the application's DB account.
psql --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=keycloak_db="$KC_DB_URL_DATABASE" \
  --set=keycloak_user="$KC_DB_USERNAME" \
  --set=keycloak_password="$KC_DB_PASSWORD" <<'EOSQL'
CREATE ROLE :"keycloak_user" LOGIN PASSWORD :'keycloak_password';
CREATE DATABASE :"keycloak_db" OWNER :"keycloak_user";
EOSQL
