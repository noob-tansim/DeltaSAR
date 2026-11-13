# DeltaSAR API (Render). Small image: the API only samples pre-computed rasters; no GDAL build needed
# (rasterio wheels bundle it). The heavy science pipeline (h5py, Earth Engine, scikit-learn) is not installed here.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DELTASAR_OUTPUTS=/app/deploy_data

WORKDIR /app
COPY requirements-deploy.txt .
RUN pip install -r requirements-deploy.txt

COPY src ./src
COPY jobs ./jobs
COPY data ./data
COPY deploy_data ./deploy_data

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "-c", "uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
