# Creates ignored, local-only demo test inputs from existing local development
# values. It intentionally writes no values to stdout.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envDir = Join-Path $root 'docker/env'

function Read-EnvFile([string]$Path) {
  $values = @{}
  Get-Content -LiteralPath $Path | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $values[$matches[1]] = $matches[2] }
  }
  return $values
}
function Put-Env([string]$Path, [hashtable]$Values) {
  $lines = @(
    $Values.GetEnumerator() | Sort-Object Name |
      ForEach-Object { "$($_.Name)=$($_.Value)" }
  )
  [System.IO.File]::WriteAllLines(
    $Path,
    [string[]]$lines,
    [System.Text.UTF8Encoding]::new($false)
  )
}
function ComposeLiteral([string]$Value) {
  # Compose interpolates $ in non-raw env_file values. URL consumers use %24.
  return $Value.Replace('$', '$$')
}

$app = Read-EnvFile (Join-Path $envDir '.env.app')
$postgres = Read-EnvFile (Join-Path $envDir '.env.postgres')
$redis = Read-EnvFile (Join-Path $envDir '.env.redis')
$rabbit = Read-EnvFile (Join-Path $envDir '.env.rabbitmq')

Copy-Item -LiteralPath (Join-Path $envDir '.env.demo.runtime.example') -Destination (Join-Path $envDir '.env.demo.runtime') -Force

$pg = @{ POSTGRES_HOST='pgvector'; POSTGRES_PORT='5432'; POSTGRES_USER=$postgres.POSTGRES_USER; POSTGRES_PASSWORD=$postgres.POSTGRES_PASSWORD; POSTGRES_DB='mini_rag_demo' }
$rd = @{ REDIS_PASSWORD=$redis.REDIS_PASSWORD }
$rb = @{ RABBITMQ_DEFAULT_USER='mini_rag_demo'; RABBITMQ_DEFAULT_PASS=$rabbit.RABBITMQ_DEFAULT_PASS; RABBITMQ_DEFAULT_VHOST='/' }
$rabbitPassword = [uri]::EscapeDataString($rabbit.RABBITMQ_DEFAULT_PASS)
$redisPassword = [uri]::EscapeDataString($redis.REDIS_PASSWORD)
$broker = "amqp://mini_rag_demo:$rabbitPassword@rabbitmq:5672/%2F"
$result = "redis://:$redisPassword@redis:6379/0"

Put-Env (Join-Path $envDir '.env.demo.postgres') $pg
# Redis and RabbitMQ use Compose's raw env-file mode, so their literal
# passwords must not be escaped here.
Put-Env (Join-Path $envDir '.env.demo.redis') @{ REDIS_PASSWORD=$redis.REDIS_PASSWORD }
Put-Env (Join-Path $envDir '.env.demo.rabbitmq') @{ RABBITMQ_DEFAULT_USER='mini_rag_demo'; RABBITMQ_DEFAULT_PASS=$rabbit.RABBITMQ_DEFAULT_PASS; RABBITMQ_DEFAULT_VHOST='/' }
Put-Env (Join-Path $envDir '.env.demo.keycloak-db') @{ KC_DB_URL_DATABASE='mini_rag_keycloak'; KC_DB_USERNAME='mini_rag_keycloak'; KC_DB_PASSWORD=(ComposeLiteral $postgres.POSTGRES_PASSWORD) }
Put-Env (Join-Path $envDir '.env.demo.keycloak') @{ KC_BOOTSTRAP_ADMIN_USERNAME='demo-admin'; KC_BOOTSTRAP_ADMIN_PASSWORD=(ComposeLiteral $postgres.POSTGRES_PASSWORD); KC_DB='postgres'; KC_DB_URL_HOST='pgvector'; KC_DB_URL_DATABASE='mini_rag_keycloak'; KC_DB_USERNAME='mini_rag_keycloak'; KC_DB_PASSWORD=(ComposeLiteral $postgres.POSTGRES_PASSWORD); KC_HOSTNAME='http://id.demo.test'; KC_HEALTH_ENABLED='true' }
Put-Env (Join-Path $envDir '.env.demo.provisioner') @{ DEMO_APP_DOMAIN='demo.test'; DEMO_KEYCLOAK_ADMIN_USERNAME='demo-admin'; DEMO_KEYCLOAK_ADMIN_PASSWORD=(ComposeLiteral $postgres.POSTGRES_PASSWORD); DEMO_USER_USERNAME='demo.user'; DEMO_USER_PASSWORD=(ComposeLiteral $postgres.POSTGRES_PASSWORD) }
Put-Env (Join-Path $envDir '.env.demo.provisioner-runtime') @{ CELERY_BROKER_URL=$broker; CELERY_RESULT_BACKEND=$result; DEMO_PROVISION_TIMEOUT_SECONDS='900' }
Put-Env (Join-Path $envDir '.env.demo.worker-file') @{ AUTHZ_ENABLED='true'; CELERY_BROKER_URL=$broker; CELERY_RESULT_BACKEND=$result }
Put-Env (Join-Path $envDir '.env.demo.worker-maintenance') @{ AUTHZ_ENABLED='true'; CELERY_BROKER_URL=$broker; CELERY_RESULT_BACKEND=$result; AUTH_SESSION_REDIS_URL="redis://:$redisPassword@redis:6379/1" }
Put-Env (Join-Path $envDir '.env.demo.worker-index') @{ AUTHZ_ENABLED='true'; CELERY_BROKER_URL=$broker; CELERY_RESULT_BACKEND=$result; OPENAI_API_KEY=$app.OPENAI_API_KEY; OPENAI_KEY=$app.OPENAI_KEY }
Put-Env (Join-Path $envDir '.env.demo-app') @{ OPENAI_API_KEY=$app.OPENAI_API_KEY; OPENAI_KEY=$app.OPENAI_KEY; CELERY_BROKER_URL=$broker; CELERY_RESULT_BACKEND=$result; AUTH_ENABLED='true'; AUTH_MODE='bff_oidc'; AUTHZ_ENABLED='true'; AUTH_SESSION_REDIS_URL="redis://:$redisPassword@redis:6379/1"; AUTH_COOKIE_SECURE='false'; AUTH_COOKIE_SAMESITE='lax'; AUTH_FRONTEND_SUCCESS_URL='/'; AUTH_OIDC_ISSUER='http://id.demo.test/realms/mini-rag'; AUTH_OIDC_CLIENT_ID='mini-rag-bff'; AUTH_OIDC_REDIRECT_URI='http://demo.test/api/v1/auth/callback'; AUTH_OIDC_AUTHORIZATION_ENDPOINT='http://keycloak:8080/realms/mini-rag/protocol/openid-connect/auth'; AUTH_OIDC_TOKEN_ENDPOINT='http://keycloak:8080/realms/mini-rag/protocol/openid-connect/token'; AUTH_OIDC_JWKS_URL='http://keycloak:8080/realms/mini-rag/protocol/openid-connect/certs'; DEMO_PUBLIC_MODE='true'; DEMO_PROJECT_MARKER='public-demo-workspace:v1'; SMTP_ENABLED='false' }
Put-Env (Join-Path $envDir '.env.demo.nginx') @{ DEMO_APP_DOMAIN='demo.test'; DEMO_IDP_DOMAIN='id.demo.test'; DEMO_TLS_MODE='bootstrap'; DEMO_TLS_CERT_PATH='/etc/nginx/certs/live/demo.test/fullchain.pem'; DEMO_TLS_KEY_PATH='/etc/nginx/certs/live/demo.test/privkey.pem'; DEMO_UPLOAD_MAX_BODY_SIZE='5m'; DEMO_API_RATE_LIMIT='30r/m'; DEMO_CHAT_RATE_LIMIT='2r/m' }
