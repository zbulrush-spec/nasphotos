FROM python:3.11-slim AS recognition-wheels
RUN sed -i 's|http://deb.debian.org|https://mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt requirements-recognition.txt ./
RUN pip wheel --no-cache-dir --index-url https://mirrors.ustc.edu.cn/pypi/simple --wheel-dir /wheels -r requirements.txt -r requirements-recognition.txt
FROM python:3.11-slim AS bundled-face-model
COPY scripts/fetch-face-model.py /build/fetch-face-model.py
RUN python /build/fetch-face-model.py /opt/insightface/models/buffalo_l

FROM python:3.11-slim AS runtime-deps
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MEDIA_ROOT=/media INSIGHTFACE_ROOT=/opt/insightface OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
RUN sed -i 's|http://deb.debian.org|https://mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 install -y --no-install-recommends ffmpeg libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-recognition.txt ./
RUN --mount=type=bind,from=recognition-wheels,source=/wheels,target=/wheels pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt -r requirements-recognition.txt

FROM runtime-deps
ENV NO_ALBUMENTATIONS_UPDATE=1
COPY --from=bundled-face-model /opt/insightface /opt/insightface
COPY app.py storage.py recognition.py ./
COPY templates templates
COPY static static
COPY vendor vendor
COPY scripts/container-entrypoint.py scripts/container-entrypoint.py
VOLUME ["/config"]
LABEL org.opencontainers.image.title="NAS Photos" \
      org.opencontainers.image.source="https://github.com/zbulrush-spec/nasphotos"
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/status', timeout=3)"
CMD ["python","scripts/container-entrypoint.py"]
