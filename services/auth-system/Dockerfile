FROM python:3.11-slim
ARG DEBIAN_FRONTEND=noninteractive
# -----------------------------
# Environment variables
# -----------------------------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# -----------------------------
# Install dependencies + Postgres client
# -----------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Set working directory
# -----------------------------
WORKDIR /app

# -----------------------------
# Install Python dependencies
# -----------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------
# Copy project files
# -----------------------------
COPY . .

# -----------------------------
# Copy entrypoint and make executable
# -----------------------------
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# -----------------------------
# Expose ports
# -----------------------------
EXPOSE 8011
EXPOSE 8012

# -----------------------------
# Signal-safe entrypoint
# -----------------------------
ENTRYPOINT ["/entrypoint.sh"]
