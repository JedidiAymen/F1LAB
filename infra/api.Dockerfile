# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
# Run source through PYTHONPATH to preserve existing repo-relative artifact
# contracts. Keeping dependencies separate makes code-only rebuilds small.

FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home racelab
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# Existing artifact resolvers derive /app/data from /app/src; retain that layout.
COPY --from=build /app/src /app/src
COPY --from=build /app/uv.lock /app/uv.lock
COPY docs/research/evidence/forecast_debug_20261031 /app/docs/research/evidence/forecast_debug_20261031
COPY docs/research/evidence/forecast_debug_paired_20261031 /app/docs/research/evidence/forecast_debug_paired_20261031
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["uvicorn", "f1_racelab.api:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "10"]
