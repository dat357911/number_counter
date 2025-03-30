FROM python:3.9-slim

# Cài đặt các dependencies hệ thống
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    libleptonica-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Kiểm tra cài đặt Poppler và Tesseract
RUN pdftoppm -v && \
    tesseract --version

# Tạo và set working directory
WORKDIR /app

# Copy requirements và cài đặt Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code
COPY . .

# Tạo các thư mục cần thiết và set quyền
RUN mkdir -p temp archive temp/debug && \
    chmod -R 777 temp archive temp/debug && \
    chmod -R 777 /app

# Set environment variables
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata
ENV PATH="/usr/bin:${PATH}"

# Kiểm tra lại quyền và thư mục
RUN ls -la /app && \
    ls -la /app/temp && \
    ls -la /app/archive && \
    tesseract --version && \
    pdftoppm -v

# Start command
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "300", "wsgi:application"] 