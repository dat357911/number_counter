FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    libleptonica-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Verify installations
RUN which pdftoppm && pdftoppm -v
RUN which tesseract && tesseract --version

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/temp /app/archive /app/temp/debug && \
    chmod -R 777 /app/temp && \
    chmod -R 777 /app/archive && \
    chmod -R 777 /app/temp/debug

# Set environment variables
ENV PYTHONPATH=/app
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata
ENV PATH="/usr/local/bin:/usr/bin:${PATH}"

# Verify final setup
RUN ls -la /app && \
    ls -la /app/temp && \
    ls -la /app/archive && \
    ls -la /app/temp/debug && \
    tesseract --version && \
    pdftoppm -v

# Start command with increased timeout
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "300", "wsgi:application"] 