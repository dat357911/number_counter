FROM python:3.9-slim

# Cài đặt các dependencies hệ thống
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Tạo và set working directory
WORKDIR /app

# Copy requirements và cài đặt Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code
COPY . .

# Tạo các thư mục cần thiết
RUN mkdir -p temp archive temp/debug && \
    chmod -R 755 temp archive

# Set environment variables
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Start command
CMD ["gunicorn", "wsgi:application"] 