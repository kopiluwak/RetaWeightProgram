# Backend container for AWS App Runner.
# Python 3.12 (stable wheels for all deps — avoids the 3.14 build issues).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; asyncpg/pydantic ship wheels for 3.12.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

# App Runner sends traffic to port 8080 by default.
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
