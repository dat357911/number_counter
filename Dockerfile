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

# Verify installations and show paths
RUN which tesseract && \
    tesseract --version && \
    which pdftoppm && \
    pdftoppm -v && \
    echo "Tesseract path: $(which tesseract)" && \
    echo "Poppler path: $(which pdftoppm)"

# Set working directory
WORKDIR /opt/render/project/src

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p temp archive temp/debug && \
    chmod -R 777 temp && \
    chmod -R 777 archive && \
    chmod -R 777 temp/debug

# Set environment variables
ENV PYTHONPATH=/opt/render/project/src
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata
ENV PATH="/usr/local/bin:/usr/bin:/opt/render/project/src:${PATH}"

# Verify final setup
RUN echo "Current PATH: $PATH" && \
    echo "Tesseract location: $(which tesseract)" && \
    echo "Tesseract version: $(tesseract --version)" && \
    echo "Poppler location: $(which pdftoppm)" && \
    echo "Poppler version: $(pdftoppm -v)" && \
    ls -la /usr/bin/tesseract && \
    ls -la /usr/bin/pdftoppm

# Start command with increased timeout
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "300", "wsgi:application"] 