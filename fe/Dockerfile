FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# (Optional) build tools nếu lib nào cần biên dịch
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài libs trước để cache tốt hơn
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy toàn bộ FE code vào image
COPY . /app

# Streamlit headless cho server
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8080
CMD ["streamlit","run","streamlit_app.py","--server.address=0.0.0.0","--server.port=8080","--server.enableCORS=false","--server.enableXsrfProtection=false"]
