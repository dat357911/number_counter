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

# Create symbolic links to ensure binaries are in PATH
RUN ln -s /usr/bin/tesseract /usr/local/bin/tesseract && \
    ln -s /usr/bin/pdftoppm /usr/local/bin/pdftoppm

# Set environment variables
ENV PYTHONPATH=/opt/render/project/src
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata
ENV PATH="/usr/local/bin:/usr/bin:/opt/render/project/src:${PATH}"

# Verify installations
RUN echo "Current PATH: $PATH" && \
    echo "Tesseract location: $(which tesseract)" && \
    echo "Tesseract version: $(tesseract --version)" && \
    echo "Poppler location: $(which pdftoppm)" && \
    echo "Poppler version: $(pdftoppm -v)" && \
    ls -la /usr/bin/tesseract && \
    ls -la /usr/local/bin/tesseract && \
    ls -la /usr/bin/pdftoppm && \
    ls -la /usr/local/bin/pdftoppm

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

# Final verification
RUN echo "Final PATH: $PATH" && \
    echo "Final Tesseract location: $(which tesseract)" && \
    echo "Final Tesseract version: $(tesseract --version)" && \
    echo "Final Poppler location: $(which pdftoppm)" && \
    echo "Final Poppler version: $(pdftoppm -v)"

# Start command with increased timeout
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "300", "wsgi:application"] 