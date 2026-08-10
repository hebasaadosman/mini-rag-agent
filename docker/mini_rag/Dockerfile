FROM ghcr.io/astral-sh/uv:0.6.14-python3.11-bookworm

WORKDIR /app

# Install additional system dependencies for lxml and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libavif-dev pkg-config \
    libjpeg-dev \
    gcc unzip zip \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY  src/requirements.txt .

RUN uv pip install  -r requirements.txt --system  


COPY src/ .

RUN mkdir -p models/db_schemes/mini_rag

COPY docker/mini_rag/alembic.example.ini /app/models/db_schemes/mini_rag/alembic.ini

COPY docker/mini_rag/entrypoint.sh /entrypoint.sh

RUN sed -i 's/\r$//' /entrypoint.sh \
    && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
