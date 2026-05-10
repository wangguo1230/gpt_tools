FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GPT_TOOLS_BACKEND_HOST=0.0.0.0 \
    GPT_TOOLS_BACKEND_PORT=18777 \
    GPT_TOOLS_BACKEND_RELOAD=0

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
RUN mkdir -p /app/data

EXPOSE 18777

CMD ["python", "run.py"]
