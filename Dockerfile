FROM python:3.11-slim-bullseye

# uv binary (pinned for reproducibility) — drives dependency install from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /uvx /usr/local/bin/

# Install system dependencies (Pillow/lxml native libs + build/runtime tools)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    libwebp-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    zlib1g-dev \
    libxml2-dev \
    libxslt1-dev \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for mercury-parser
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install mercury-parser globally
RUN npm install -g @postlight/mercury-parser

WORKDIR /app

# uv build configuration:
# - compile bytecode for faster container startup
# - copy link mode (bind mounts are unavailable across image layers)
# - never download a managed interpreter; use the image's system Python 3.11
# - put the project venv on PATH so `python mywi.py` resolves to it unchanged
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# ENV PATH covers exec-form entrypoints and `docker compose exec mwi python ...`,
# but a login shell (the `mwi-run` service uses entrypoint ["bash","-lc"]) re-sources
# /etc/profile and would clobber PATH. Export the venv via profile.d so login shells
# resolve `python` to the project venv too — keeps docker-compose.yml unchanged.
RUN printf '%s\n' 'export PATH="/app/.venv/bin:$PATH"' > /etc/profile.d/10-uv-venv.sh

# Install dependencies from the lockfile (reproducible, no dev tooling).
# Copied before the source so this layer is cached across code changes.
# package=false → uv installs deps only and does not need the source tree.
# WITH_ML=1 adds the optional ML extras (FAISS + transformers/torch).
COPY pyproject.toml uv.lock .python-version ./
ARG WITH_ML=0
RUN uv sync --frozen --no-dev $([ "$WITH_ML" = "1" ] && echo "--extra ml")

# Pre-download NLTK data to avoid repeated downloads (venv Python is on PATH)
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"

COPY . .

# Optionally install Playwright browsers inside the image
ARG WITH_PLAYWRIGHT_BROWSERS=0
RUN if [ "$WITH_PLAYWRIGHT_BROWSERS" = "1" ]; then python install_playwright.py; fi

CMD ["tail", "-f", "/dev/null"]
