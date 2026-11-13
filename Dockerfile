FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MEDIA_ROOT=/media
RUN sed -i 's|http://deb.debian.org|https://mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://mirrors.ustc.edu.cn/pypi/simple -r requirements.txt
COPY app.py storage.py ./
COPY templates templates
COPY static static
VOLUME ["/config"]
LABEL org.opencontainers.image.title="NAS Photos" \
      org.opencontainers.image.source="https://github.com/zbulrush-spec/nasphotos"
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/status', timeout=3)"
CMD ["gunicorn","--bind","0.0.0.0:8080","--workers","1","--threads","4","--timeout","120","app:app"]
