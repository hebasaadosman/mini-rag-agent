import time

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.middleware.base import BaseHTTPMiddleware


REQUEST_COUNT = Counter(
    "request_count",
    "Total number of requests",
    ["method", "endpoint", "http_status"],
)

REQUEST_LATENCY = Histogram(
    "request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)

REQUESTS_IN_PROGRESS = Gauge(
    "requests_in_progress",
    "Number of requests currently being processed",
    ["method", "endpoint"],
)


class PrometheusMiddlewareCustom(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path

        REQUESTS_IN_PROGRESS.labels(
            method=method,
            endpoint=endpoint,
        ).inc()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                http_status=str(response.status_code),
            ).inc()

            return response

        finally:
            process_time = time.perf_counter() - start_time

            REQUEST_LATENCY.labels(
                method=method,
                endpoint=endpoint,
            ).observe(process_time)

            REQUESTS_IN_PROGRESS.labels(
                method=method,
                endpoint=endpoint,
            ).dec()


def setup_metrics_route(app: FastAPI) -> None:
    app.add_middleware(PrometheusMiddlewareCustom)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )