FROM python:3.13-slim-trixie
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libcurl4t64 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY model_config.json .
COPY scripts/setup.py scripts/setup.py
RUN python scripts/setup.py
COPY app app
COPY static static
COPY scripts/run.py scripts/run.py
ENV ANALYZER_HOST=0.0.0.0 PYTHONUNBUFFERED=1 ANALYZER_DATA_DIR=/app/data
EXPOSE 8000
CMD ["python", "scripts/run.py"]
