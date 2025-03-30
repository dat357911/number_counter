import os
import sys
import subprocess
import logging
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
import pytz

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        # Check Tesseract
        tesseract_path = subprocess.check_output(['which', 'tesseract']).decode().strip()
        tesseract_version = subprocess.check_output(['tesseract', '--version']).decode().strip()
        logger.info(f"Tesseract found at: {tesseract_path}")
        logger.info(f"Tesseract version: {tesseract_version}")
        
        # Check Poppler
        pdftoppm_path = subprocess.check_output(['which', 'pdftoppm']).decode().strip()
        pdftoppm_version = subprocess.check_output(['pdftoppm', '-v']).decode().strip()
        logger.info(f"Poppler found at: {pdftoppm_path}")
        logger.info(f"Poppler version: {pdftoppm_version}")
        
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking dependencies: {str(e)}")
        logger.error("Required dependencies are not installed properly!")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking dependencies: {str(e)}")
        return False

def ensure_dir(directory):
    """Ensure directory exists with proper permissions"""
    try:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")
        else:
            logger.info(f"Directory exists: {directory}")
        
        # Set permissions to 777
        os.chmod(directory, 0o777)
        
        # Verify permissions
        mode = os.stat(directory).st_mode
        logger.info(f"Directory permissions for {directory}: {oct(mode & 0o777)}")
        
        return True
    except Exception as e:
        logger.error(f"Error ensuring directory {directory}: {str(e)}")
        return False

# Add project directory to Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.append(project_dir)
    logger.info(f"Added project directory to Python path: {project_dir}")

# Create necessary directories
base_dir = os.getenv('RENDER_APP_DIR', project_dir)
temp_dir = os.path.join(base_dir, 'temp')
archive_dir = os.path.join(base_dir, 'archive')
debug_dir = os.path.join(temp_dir, 'debug')

# Create directories with proper permissions
for directory in [temp_dir, archive_dir, debug_dir]:
    ensure_dir(directory)

# Check dependencies before running the application
if not check_dependencies():
    logger.error("Failed to verify required dependencies. Application may not function correctly.")
    sys.exit(1)

# Set environment variables
os.environ['LANG'] = 'C.UTF-8'
os.environ['LC_ALL'] = 'C.UTF-8'

# Add Poppler and Tesseract to PATH based on environment
if os.name == 'nt':  # Windows
    poppler_path = r'C:\Program Files\poppler-23.11.0\Library\bin'
    tesseract_path = r'C:\Program Files\Tesseract-OCR'
    if os.path.exists(poppler_path):
        os.environ['PATH'] = poppler_path + os.pathsep + os.environ.get('PATH', '')
        logger.info(f"Added Poppler to PATH: {poppler_path}")
    if os.path.exists(tesseract_path):
        os.environ['PATH'] = tesseract_path + os.pathsep + os.environ.get('PATH', '')
        logger.info(f"Added Tesseract to PATH: {tesseract_path}")
else:  # Linux/Unix
    os.environ['PATH'] = '/usr/bin:/usr/local/bin:' + os.environ.get('PATH', '')
    logger.info("Added system binary paths to PATH")

from app import app as application

if __name__ == "__main__":
    application.run() 