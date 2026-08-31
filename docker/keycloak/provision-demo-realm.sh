#!/bin/sh
set -eu

KCADM=/opt/keycloak/bin/kcadm.sh
REALM=mini-rag

"$KCADM" config credentials \
  --server http://keycloak:8080 \
  --realm master \
  --user "$DEMO_KEYCLOAK_ADMIN_USERNAME" \
  --password "$DEMO_KEYCLOAK_ADMIN_PASSWORD" >/dev/null

if ! "$KCADM" get "realms/$REALM" >/dev/null 2>&1; then
  "$KCADM" create realms -s realm="$REALM" -s enabled=true -s registrationAllowed=false
fi

if ! "$KCADM" get roles/demo_user -r "$REALM" >/dev/null 2>&1; then
  "$KCADM" create roles -r "$REALM" -s name=demo_user -s description='Limited public demo account'
fi

CLIENT_ID="$("$KCADM" get clients -r "$REALM" -q clientId=mini-rag-bff --fields id --format csv --noquotes 2>/dev/null || true)"
if [ -z "$CLIENT_ID" ]; then
  "$KCADM" create clients -r "$REALM" \
    -s clientId=mini-rag-bff \
    -s enabled=true \
    -s publicClient=true \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=false \
    -s serviceAccountsEnabled=false \
    -s implicitFlowEnabled=false \
    -s 'attributes."pkce.code.challenge.method"=S256' \
    -s "redirectUris=[\"https://${DEMO_APP_DOMAIN}/api/v1/auth/callback\"]" \
    -s "webOrigins=[\"https://${DEMO_APP_DOMAIN}\"]"
  CLIENT_ID="$("$KCADM" get clients -r "$REALM" -q clientId=mini-rag-bff --fields id --format csv --noquotes)"
fi

if ! "$KCADM" get "clients/$CLIENT_ID/protocol-mappers/models" -r "$REALM" | grep -q '"claim.name" : "roles"'; then
  "$KCADM" create "clients/$CLIENT_ID/protocol-mappers/models" -r "$REALM" \
    -s name='realm roles for BFF' \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-usermodel-realm-role-mapper \
    -s consentRequired=false \
    -s 'config."claim.name"=roles' \
    -s 'config."jsonType.label"=String' \
    -s 'config.multivalued=true' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' \
    -s 'config."userinfo.token.claim"=true'
fi

USER_ID="$("$KCADM" get users -r "$REALM" -q username="$DEMO_USER_USERNAME" --fields id --format csv --noquotes 2>/dev/null || true)"
if [ -z "$USER_ID" ]; then
  "$KCADM" create users -r "$REALM" \
    -s username="$DEMO_USER_USERNAME" -s enabled=true -s emailVerified=true
  USER_ID="$("$KCADM" get users -r "$REALM" -q username="$DEMO_USER_USERNAME" --fields id --format csv --noquotes)"
fi

"$KCADM" set-password -r "$REALM" --userid "$USER_ID" --new-password "$DEMO_USER_PASSWORD" >/dev/null
"$KCADM" add-roles -r "$REALM" --uusername "$DEMO_USER_USERNAME" --rolename demo_user >/dev/null

echo "Demo realm provisioned without platform_admin."
