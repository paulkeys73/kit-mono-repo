FROM python:3.11-slim
ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir requests beautifulsoup4 urllib3

COPY . .

CMD ["python", "main.py", "list-steps"]
