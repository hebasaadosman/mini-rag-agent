# Build the Angular application once, then serve only its static output.
FROM node:24-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build -- --configuration production

FROM nginx:1.27-alpine

COPY --from=frontend-build /frontend/dist/frontend/browser/ /usr/share/nginx/html/
COPY docker/nginx/bootstrap.conf.template /opt/demo-nginx/bootstrap.conf.template
COPY docker/nginx/demo.conf.template /opt/demo-nginx/tls.conf.template
COPY docker/nginx/select-demo-config.sh /docker-entrypoint.d/10-select-demo-config.sh
RUN mkdir -p /etc/nginx/templates \
    && chmod +x /docker-entrypoint.d/10-select-demo-config.sh
