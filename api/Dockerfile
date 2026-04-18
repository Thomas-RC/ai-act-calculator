FROM python:3.12-slim

# WeasyPrint wymaga systemowych bibliotek do renderowania PDF
# (pango, cairo, pangoft2, fontconfig, dejavu-fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Zależności Pythona
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kod aplikacji
COPY api/ ./

# Korpus prawny (fallback + raw jako wolumen)
COPY legal_sources /legal_sources

# Skrypt refresh
COPY scripts /scripts

ENV PYTHONUNBUFFERED=1 \
    LEGAL_SOURCES_DIR=/legal_sources \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
