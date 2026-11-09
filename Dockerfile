FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HDT_HOST=0.0.0.0 \
    HDT_PORT=8000
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system hdt \
    && useradd --system --gid hdt --home-dir /app hdt
COPY --chown=hdt:hdt . /app
RUN mkdir -p /app/runtime && chown -R hdt:hdt /app/runtime
USER hdt
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD python -c "import os,urllib.request; req=urllib.request.Request('http://127.0.0.1:8000/api/health',headers={'Authorization':'Bearer '+os.environ['HDT_HEALTH_TOKEN']}); urllib.request.urlopen(req,timeout=3).read()" || exit 1
CMD ["python", "app.py"]
