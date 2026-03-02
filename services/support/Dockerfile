FROM python:3.11-slim
ARG DEBIAN_FRONTEND=noninteractive
# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose Alert Server port
EXPOSE 8099

# Use JSON-form CMD (signal-safe)
CMD ["bash", "start.sh"]
