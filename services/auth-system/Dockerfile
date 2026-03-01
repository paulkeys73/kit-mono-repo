FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY Django-Allauth/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY Django-Allauth/ .

RUN chmod +x entrypoint.sh

EXPOSE 8034

ENTRYPOINT ["bash", "entrypoint.sh"]
