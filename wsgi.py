import os
import sys
import logging

# Cấu hình logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Add your project directory to Python path 
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.append(project_dir)
    logging.info(f"Added project directory to Python path: {project_dir}")

# Set environment variables
os.environ['LANG'] = 'C.UTF-8'
os.environ['LC_ALL'] = 'C.UTF-8'

def ensure_dir(directory):
    """Đảm bảo thư mục tồn tại và có quyền truy cập"""
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            os.chmod(directory, 0o755)
            logging.info(f"Created directory with permissions: {directory}")
        except Exception as e:
            logging.error(f"Error creating directory {directory}: {str(e)}")
            raise

# Create required directories with absolute paths
temp_dir = os.path.join(project_dir, 'temp')
archive_dir = os.path.join(project_dir, 'archive')
debug_dir = os.path.join(temp_dir, 'debug')

# Create directories if they don't exist
for directory in [temp_dir, archive_dir, debug_dir]:
    ensure_dir(directory)
    logging.info(f"Directory exists and accessible: {directory}")

# Add Poppler and Tesseract to PATH for Windows
if os.name == 'nt':  # Windows
    poppler_path = r'C:\Program Files\poppler-23.11.0\Library\bin'
    tesseract_path = r'C:\Program Files\Tesseract-OCR'
    if os.path.exists(poppler_path):
        os.environ['PATH'] = poppler_path + os.pathsep + os.environ.get('PATH', '')
        logging.info(f"Added Poppler to PATH: {poppler_path}")
    if os.path.exists(tesseract_path):
        os.environ['PATH'] = tesseract_path + os.pathsep + os.environ.get('PATH', '')
        logging.info(f"Added Tesseract to PATH: {tesseract_path}")
else:  # Linux/Unix
    os.environ['PATH'] = '/usr/bin:/usr/local/bin:' + os.environ.get('PATH', '')
    logging.info("Added system binary paths to PATH")

from app import app as application 