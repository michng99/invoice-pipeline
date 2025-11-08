FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
RUN python -m pip install --upgrade --no-cache-dir "pip==25.3.*"
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
EXPOSE 8080
CMD ["streamlit","run","streamlit_app.py","--server.address=0.0.0.0","--server.port=8080","--server.enableCORS=false","--server.enableXsrfProtection=false"]
