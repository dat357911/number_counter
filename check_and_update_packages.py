import pkg_resources
import subprocess
import sys
import os

def check_package_version(package_name):
    try:
        version = pkg_resources.get_distribution(package_name).version
        return version
    except pkg_resources.DistributionNotFound:
        return None

def update_package(package_name):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package_name])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    # Danh sách các package cần kiểm tra
    packages = [
        'Flask',
        'Werkzeug',
        'PyPDF2',
        'pdf2image',
        'pytesseract',
        'Pillow',
        'APScheduler'
    ]
    
    print("=== Kiểm tra phiên bản các thư viện ===\n")
    
    for package in packages:
        current_version = check_package_version(package)
        if current_version:
            print(f"{package}: {current_version}")
        else:
            print(f"{package}: Chưa cài đặt")
    
    print("\n=== Cập nhật các thư viện ===\n")
    
    for package in packages:
        print(f"Đang cập nhật {package}...")
        if update_package(package):
            new_version = check_package_version(package)
            print(f"✓ Đã cập nhật {package} lên phiên bản {new_version}")
        else:
            print(f"✗ Lỗi khi cập nhật {package}")
    
    print("\n=== Kiểm tra Poppler và Tesseract ===\n")
    
    # Kiểm tra Poppler
    try:
        if os.name == 'nt':  # Windows
            poppler_paths = [
                r'C:\Program Files\poppler-23.11.0\Library\bin',
                r'C:\Program Files (x86)\poppler-23.11.0\Library\bin',
                r'C:\poppler-23.11.0\Library\bin'
            ]
            poppler_found = any(os.path.exists(path) for path in poppler_paths)
        else:  # Linux/Mac
            poppler_found = subprocess.run(['which', 'pdftoppm'], capture_output=True).returncode == 0
        
        if poppler_found:
            print("✓ Poppler đã được cài đặt")
        else:
            print("✗ Poppler chưa được cài đặt")
    except Exception as e:
        print(f"✗ Lỗi khi kiểm tra Poppler: {e}")
    
    # Kiểm tra Tesseract
    try:
        if os.name == 'nt':  # Windows
            tesseract_paths = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                r'C:\Tesseract-OCR\tesseract.exe'
            ]
            tesseract_found = any(os.path.exists(path) for path in tesseract_paths)
        else:  # Linux/Mac
            tesseract_found = subprocess.run(['which', 'tesseract'], capture_output=True).returncode == 0
        
        if tesseract_found:
            print("✓ Tesseract đã được cài đặt")
        else:
            print("✗ Tesseract chưa được cài đặt")
    except Exception as e:
        print(f"✗ Lỗi khi kiểm tra Tesseract: {e}")

if __name__ == "__main__":
    main() 