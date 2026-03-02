FROM python:3.11-slim
ARG DEBIAN_FRONTEND=noninteractive
# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Expose Auth Service port
EXPOSE 8034

# Use signal-safe entrypoint
ENTRYPOINT ["bash", "entrypoint.sh"]
