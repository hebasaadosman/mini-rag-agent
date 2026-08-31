#!/bin/sh
set -eu
case "${DEMO_TLS_MODE:-bootstrap}" in
  bootstrap) cp /opt/demo-nginx/bootstrap.conf.template /etc/nginx/templates/default.conf.template ;;
  tls) cp /opt/demo-nginx/tls.conf.template /etc/nginx/templates/default.conf.template ;;
  *) echo "DEMO_TLS_MODE must be bootstrap or tls" >&2; exit 1 ;;
esac
