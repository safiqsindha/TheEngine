# The Engine — Live Scout Mode A worker image
# Team 2950 — The Devastators
#
# Multi-stage build:
#   1. builder  — installs Python deps into a venv (caches well)
#   2. runtime  — slim image with just the venv + app source + ffmpeg
#
# The image bakes PaddleOCR + paddlepaddle + opencv-headless so the
# Container App Job has zero cold-start dependency fetches. Image size
# is dominated by paddlepaddle (~250 MB) and opencv-headless (~70 MB);
# everything else is small.
#
# Build:
#     docker build -f workers/Dockerfile -t mode-a-worker:dev .
# Run locally (smoke test):
#     docker run --rm -e STATE_BACKEND=local mode-a-worker:dev \
#         python -m workers.mode_a --help

# ─── Stage 1: builder ───
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for any wheels that fall back to source. Most won't, but
# paddlepaddle on linux/arm64 sometimes needs these.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy requirements first so the pip layer caches across source edits
COPY workers/requirements.txt /build/requirements.txt

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /build/requirements.txt


# ─── Stage 2: runtime ───
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    STATE_BACKEND=azure

# ffmpeg is needed by hls_pull / extract_frames_from_video
# libgl1 + libglib2.0-0 are runtime deps for opencv-python-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Bring the venv over from the builder stage
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# App source — copy only what the workers need at runtime so we don't
# accidentally invalidate the layer cache on unrelated repo edits
COPY workers/         /app/workers/
COPY scout/           /app/scout/
COPY eye/             /app/eye/

# Pre-download PaddleOCR model weights so the first cron tick doesn't
# spend 10–15s pulling them from the internet. PaddleOCR caches in
# ~/.paddlex by default; we trigger a tiny dummy run to populate it.
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
RUN python -c "import sys; sys.path.insert(0, '/app/eye'); \
from overlay_ocr import OverlayOCR; \
ocr = OverlayOCR(); _ = ocr.reader" \
    || echo "warning: paddleocr model warmup skipped (will fetch at first run)"

# Container App Jobs invoke a single command per execution and exit;
# the default entrypoint is Mode A. Override at job-spec level for
# discovery / mode_b / mode_c.
ENTRYPOINT ["python", "-m"]
CMD ["workers.mode_a", "--help"]
