FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH" \
    DOCLING_ARTIFACTS_PATH=/opt/docling/models

# OpenCV, which Docling pulls in, needs these shared libraries at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# CPU torch comes from the pytorch-cpu index in pyproject.toml. Prefetch the
# layout and table weights in this layer. Hugging Face's own cache is discarded
# so the image keeps a single copy. OCR weights are not downloaded.
RUN mkdir -p /opt/docling/models \
    && HF_HOME=/tmp/hf-download python -c "from pathlib import Path; from docling.utils.model_downloader import download_models; download_models(output_dir=Path('/opt/docling/models'), progress=False, with_layout=True, with_tableformer=True, with_code_formula=False, with_picture_classifier=False, with_rapidocr=False)" \
    && rm -rf /tmp/hf-download

COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
