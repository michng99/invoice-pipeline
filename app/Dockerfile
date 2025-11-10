# Dùng image Python 3.11 hoặc 3.12
FROM python:3.12-slim

# Đặt thư mục làm việc bên trong container
WORKDIR /code

# Sao chép file requirements (giả sử app/ có file requirements.txt riêng)
COPY requirements.txt /code/requirements.txt

# Cài đặt thư viện
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
RUN pip install gunicorn uvicorn

# Sao chép toàn bộ code app (BE) vào
COPY . /code

# Cổng mà Gunicorn sẽ chạy (cổng chuẩn của Cloud Run)
EXPOSE 8080

# Lệnh chạy app khi container khởi động
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8080"]