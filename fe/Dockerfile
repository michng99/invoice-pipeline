FROM python:3.12-slim

# System deps (đủ dùng cho Streamlit)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl bash ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirement và cài deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy FE source
COPY . /app

# Streamlit config
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# BACKEND_URL sẽ truyền khi deploy
# ENV BACKEND_URL="https://invoice-pipeline-160913806.asia-southeast1.run.app"

EXPOSE 8080
CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8080", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
