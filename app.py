from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, Response, stream_with_context, session
import os
from werkzeug.utils import secure_filename
import PyPDF2
from pdf2image import convert_from_path
import pytesseract
import re
from PIL import Image, ImageEnhance
import io
import shutil
from datetime import datetime, timedelta
import time
import json
import platform
import logging
import sys
from functools import wraps
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

# Cấu hình logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Cấu hình đường dẫn
if platform.system() == 'Windows':
    POPPLER_BASE = r'C:\Program Files\poppler-23.11.0'
    POPPLER_PATH = os.path.join(POPPLER_BASE, 'Library', 'bin')
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    # Cấu hình cho Linux
    POPPLER_PATH = '/usr/bin'
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# Kiểm tra các file cần thiết
REQUIRED_FILES = [
    'pdftoppm.exe',
    'pdfinfo.exe'
] if platform.system() == 'Windows' else []

# Biến global để theo dõi tiến trình
progress_data = {
    'total_pages': 0,
    'processed_pages': 0,
    'complete': False
}

# Danh sách tài khoản hợp lệ
VALID_ACCOUNTS = {
    'sammy': '04',
    'ryan': '04',
    'daniel': '04'
}

# Giới hạn số lượng người dùng đăng nhập đồng thời
MAX_CONCURRENT_USERS = 3

# Lưu trữ thông tin người dùng đang đăng nhập
active_users = {}

# Cấu hình database
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def init_db():
    """Khởi tạo database nếu chưa tồn tại"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Tạo bảng files để lưu thông tin file
        c.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT NOT NULL,
                processed_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                total_pages INTEGER,
                processed_pages INTEGER,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_by TEXT,
                order_numbers TEXT
            )
        ''')
        
        # Tạo bảng order_numbers để lưu chi tiết các order number
        c.execute('''
            CREATE TABLE IF NOT EXISTS order_numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                order_number TEXT NOT NULL,
                page_number INTEGER,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        
        conn.commit()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing database: {str(e)}")
    finally:
        conn.close()

def save_file_info(file_info):
    """Lưu thông tin file vào database"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Lưu thông tin file
        c.execute('''
            INSERT INTO files (
                original_name, processed_name, file_path, 
                file_size, total_pages, processed_pages,
                status, processed_by, order_numbers
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            file_info['original_name'],
            file_info['processed_name'],
            file_info['path'],
            file_info.get('file_size', 0),
            file_info.get('total_pages', 0),
            file_info.get('processed_pages', 0),
            file_info.get('status', 'completed'),
            session.get('username'),
            ','.join(file_info.get('order_numbers', []))
        ))
        
        file_id = c.lastrowid
        
        # Lưu chi tiết order numbers
        for order_number in file_info.get('order_numbers', []):
            c.execute('''
                INSERT INTO order_numbers (file_id, order_number)
                VALUES (?, ?)
            ''', (file_id, order_number))
        
        conn.commit()
        logging.info(f"File info saved to database: {file_info['original_name']}")
    except Exception as e:
        logging.error(f"Error saving file info to database: {str(e)}")
    finally:
        conn.close()

def get_file_history(limit=100):
    """Lấy lịch sử xử lý file"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        c.execute('''
            SELECT 
                id, original_name, processed_name, file_size,
                total_pages, status, created_at, processed_by,
                order_numbers
            FROM files 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        files = []
        for row in c.fetchall():
            files.append({
                'id': row[0],
                'original_name': row[1],
                'processed_name': row[2],
                'file_size': row[3],
                'total_pages': row[4],
                'status': row[5],
                'created_at': row[6],
                'processed_by': row[7],
                'order_numbers': row[8].split(',') if row[8] else []
            })
        
        return files
    except Exception as e:
        logging.error(f"Error getting file history: {str(e)}")
        return []
    finally:
        conn.close()

# Khởi tạo database khi khởi động ứng dụng
init_db()

def is_admin(username):
    return username == 'daniel'

def get_active_users():
    current_time = datetime.now()
    # Xóa các phiên đăng nhập đã hết hạn (30 phút)
    expired_users = [user for user, data in active_users.items() 
                    if (current_time - data['last_activity']).total_seconds() > 1800]
    for user in expired_users:
        del active_users[user]
    return active_users

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def check_poppler_installation():
    if platform.system() == 'Windows':
        if not os.path.exists(POPPLER_PATH):
            raise RuntimeError(f'Không tìm thấy thư mục Poppler tại {POPPLER_PATH}')
        
        missing_files = []
        for file in REQUIRED_FILES:
            if not os.path.exists(os.path.join(POPPLER_PATH, file)):
                missing_files.append(file)
        
        if missing_files:
            raise RuntimeError(f'Thiếu các file sau trong thư mục Poppler: {", ".join(missing_files)}')
            
        # Thêm thư mục bin và thư mục chứa DLL vào PATH
        if POPPLER_PATH not in os.environ['PATH']:
            os.environ['PATH'] = POPPLER_PATH + os.pathsep + os.environ['PATH']
        
        # Thêm thư mục Library vào PATH để tìm các DLL
        library_path = os.path.dirname(POPPLER_PATH)  # Lấy thư mục Library
        if library_path not in os.environ['PATH']:
            os.environ['PATH'] = library_path + os.pathsep + os.environ['PATH']
    else:
        # Kiểm tra các công cụ cần thiết trên Linux
        required_tools = ['pdftoppm', 'pdfinfo', 'tesseract']
        for tool in required_tools:
            if not shutil.which(tool):
                raise RuntimeError(f'Không tìm thấy {tool}. Vui lòng cài đặt poppler-utils và tesseract-ocr')

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Thay đổi thành một key phức tạp hơn trong production

# Cấu hình cho upload
UPLOAD_FOLDER = 'temp'
DEBUG_FOLDER = os.path.join(UPLOAD_FOLDER, 'debug')
ALLOWED_EXTENSIONS = {'pdf'}

# Đảm bảo đường dẫn tuyệt đối cho thư mục upload
app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'temp'))
app.config['MAX_CONTENT_LENGTH'] = None  # Bỏ giới hạn kích thước file

# Thêm cấu hình cho thư mục archive
ARCHIVE_FOLDER = 'archive'
app.config['ARCHIVE_FOLDER'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'archive'))

def ensure_dir(directory):
    """Đảm bảo thư mục tồn tại và có quyền truy cập"""
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            logging.info(f"Created directory: {directory}")
            # Thêm quyền ghi cho thư mục trên Windows
            if platform.system() == 'Windows':
                os.chmod(directory, 0o777)
        except Exception as e:
            logging.error(f"Error creating directory {directory}: {str(e)}")
            raise

# Đảm bảo các thư mục cần thiết tồn tại
for folder in [app.config['UPLOAD_FOLDER'], app.config['ARCHIVE_FOLDER']]:
    ensure_dir(folder)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_order_number(image):
    # Lưu ảnh gốc để debug
    debug_path = os.path.join(app.config['UPLOAD_FOLDER'], 'debug')
    if not os.path.exists(debug_path):
        os.makedirs(debug_path)

    # Crop ảnh để lấy vùng chứa Order Number
    # Dựa vào layout của file PDF từ InfoNexus, Order Number nằm trong khung nhỏ phía trên bên phải
    width, height = image.size
    
    # Crop theo tỷ lệ chính xác hơn:
    # - Chiều ngang: từ 55% đến 85% chiều rộng (tập trung vào khung chứa Order Number)
    # - Chiều dọc: từ 8% đến 15% chiều cao (vùng chứa Order Number và giá trị)
    crop_box = (
        width * 0.55,  # Left: bắt đầu từ giữa sang phải một chút
        height * 0.08, # Top: phần trên cùng của trang
        width * 0.85,  # Right: kết thúc trước lề phải
        height * 0.15  # Bottom: đủ để bao quát cả label và giá trị
    )
    cropped = image.crop(crop_box)
    
    # Lưu ảnh đã crop để debug
    cropped.save(os.path.join(debug_path, 'cropped_order.png'))
    
    # Chuyển sang ảnh grayscale và tăng độ tương phản
    cropped = cropped.convert('L')
    
    # Tăng kích thước ảnh để OCR tốt hơn (4x)
    cropped = cropped.resize((cropped.width * 4, cropped.height * 4))
    
    # Tăng độ tương phản
    enhancer = ImageEnhance.Contrast(cropped)
    cropped = enhancer.enhance(2.5)
    
    # Tăng độ sáng
    enhancer = ImageEnhance.Brightness(cropped)
    cropped = enhancer.enhance(1.7)
    
    # Lưu ảnh đã xử lý để debug
    cropped.save(os.path.join(debug_path, 'processed_order.png'))
    
    # OCR với nhiều cấu hình khác nhau
    configs = [
        '--psm 6 -c tessedit_char_whitelist=0123456789',  # Dòng đơn
        '--psm 7 -c tessedit_char_whitelist=0123456789',  # Dòng đơn, giả định một khối text
        '--psm 8 -c tessedit_char_whitelist=0123456789',  # Một từ
        '--psm 13 -c tessedit_char_whitelist=0123456789'  # Dòng đơn, raw
    ]
    
    all_texts = []
    for config in configs:
        text = pytesseract.image_to_string(cropped, config=config)
        # Loại bỏ ký tự không phải số
        text = ''.join(c for c in text if c.isdigit())
        if text:
            all_texts.append(text)
    
    print("All extracted texts from Order Number area:", all_texts)
    
    # Tìm số theo định dạng cụ thể (10 chữ số)
    patterns = [
        r'0900\d{6}',  # Tìm số bắt đầu bằng 0900 và có 6 số phía sau
        r'4500\d{6}'   # Tìm số bắt đầu bằng 4500 và có 6 số phía sau
    ]
    
    # Tìm trong tất cả các text đã trích xuất
    for text in all_texts:
        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                number = match.group(0)
                print(f"Found valid Order Number: {number}")
                return number
    
    print("No valid Order Number found in any configuration")
    return None

def extract_page_number(image):
    # Lưu ảnh gốc để debug
    debug_path = os.path.join(app.config['UPLOAD_FOLDER'], 'debug')
    if not os.path.exists(debug_path):
        os.makedirs(debug_path)
    
    # Crop phần chứa "P.X of Y" ở cuối trang
    width, height = image.size
    
    # Tìm trong phần cuối của trang
    crop_box = (
        width * 0.85,  # Left: phần bên phải
        height * 0.95, # Top: gần cuối trang
        width,         # Right: đến hết
        height        # Bottom: đến hết
    )
    cropped = image.crop(crop_box)
    
    # Lưu ảnh đã crop để debug
    cropped.save(os.path.join(debug_path, 'cropped_page.png'))
    
    # Chuyển sang ảnh grayscale
    cropped = cropped.convert('L')
    
    # Tăng kích thước ảnh để OCR tốt hơn (4x)
    cropped = cropped.resize((cropped.width * 4, cropped.height * 4))
    
    # Tăng độ tương phản
    enhancer = ImageEnhance.Contrast(cropped)
    cropped = enhancer.enhance(2.5)
    
    # Tăng độ sáng
    enhancer = ImageEnhance.Brightness(cropped)
    cropped = enhancer.enhance(1.7)
    
    # Lưu ảnh đã xử lý để debug
    cropped.save(os.path.join(debug_path, 'processed_page.png'))
    
    # OCR với cấu hình tối ưu cho text
    text = pytesseract.image_to_string(cropped)
    print("Extracted text from page number area:", text)
    
    # Tìm số trang từ text
    # Thử các mẫu khác nhau
    patterns = [
        r'P\.?\s*(\d+)\s*(?:of|/)\s*\d+',  # P.X of Y
        r'Page\s*(\d+)\s*(?:of|/)\s*\d+',   # Page X of Y
        r'P\s*(\d+)',                        # PX
        r'(\d+)\s*of\s*\d+'                 # X of Y
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                page_num = int(match.group(1))
                print(f"Found page number: {page_num}")
                return page_num
            except ValueError:
                continue
    
    # Nếu không tìm thấy theo format, thử tìm số đơn lẻ
    numbers = re.findall(r'\d+', text)
    if numbers:
        try:
            page_num = int(numbers[0])
            print(f"Found potential page number: {page_num}")
            return page_num
        except ValueError:
            pass
    
    print("No page number found")
    return 1  # Trả về 1 thay vì 999 nếu không tìm thấy

def parse_number_sequence(sequence):
    if not sequence:
        return []
    
    # Loại bỏ dấu ngoặc kép và khoảng trắng không cần thiết
    sequence = sequence.replace('"', '').replace("'", '')
    # Loại bỏ khoảng trắng và xuống dòng
    sequence = ''.join(sequence.split())
    
    numbers = set()
    parts = sequence.split(",")
    
    for part in parts:
        if not part:  # Bỏ qua phần tử rỗng
            continue
        if "-" in part:
            try:
                start, end = map(int, part.split("-"))
                numbers.update(range(start, end + 1))
            except ValueError:
                return None
        else:
            try:
                numbers.add(int(part))
            except ValueError:
                return None
    
    return sorted(list(numbers))

def check_continuity(sequence1, sequence2):
    # Kiểm tra tính liên tục giữa hai dãy số
    if not sequence1 or not sequence2:
        return False, "Một hoặc cả hai dãy số đang trống"
    
    all_numbers = sorted(sequence1 + sequence2)
    if len(all_numbers) < 2:
        return False, "Cần ít nhất hai số để kiểm tra tính liên tục"
    
    # Kiểm tra xem có số nào bị trùng giữa hai dãy không
    duplicates = set(sequence1) & set(sequence2)
    if duplicates:
        duplicate_list = sorted(list(duplicates))
        return False, f"Phát hiện số trùng nhau giữa hai dãy: {', '.join(map(str, duplicate_list))}"
    
    # Kiểm tra tính liên tục
    for i in range(len(all_numbers) - 1):
        if all_numbers[i + 1] - all_numbers[i] > 1:
            gap_start = all_numbers[i]
            gap_end = all_numbers[i + 1]
            return False, f"Phát hiện khoảng trống từ {gap_start} đến {gap_end}"
    
    return True, "Hai dãy số liên tục với nhau"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in VALID_ACCOUNTS and VALID_ACCOUNTS[username] == password:
            # Kiểm tra số lượng người dùng đang đăng nhập
            active_users_list = get_active_users()
            if len(active_users_list) >= MAX_CONCURRENT_USERS and username not in active_users_list:
                return render_template('login.html', 
                    error='Hệ thống đã đạt giới hạn số lượng người dùng đăng nhập đồng thời. Vui lòng thử lại sau.')
            
            # Lưu thông tin đăng nhập
            session['username'] = username
            active_users[username] = {
                'last_activity': datetime.now(),
                'ip_address': request.remote_addr,
                'user_agent': request.user_agent.string
            }
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error='Tên đăng nhập hoặc mật khẩu không đúng')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username')
    if username:
        if username in active_users:
            del active_users[username]
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return render_template('index.html')

@app.route('/number-analysis')
@login_required
def number_analysis():
    return render_template('number_analysis.html')

@app.route('/data-analysis')
@login_required
def data_analysis():
    return render_template('data_analysis.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        mode = request.form.get('mode')
        logging.info(f"Received request with mode: {mode}")
        
        if mode == 'single':
            numbers = request.form.get('numbers', '')
            logging.info(f"Received numbers: {numbers}")
            parsed_numbers = parse_number_sequence(numbers)
            
            if parsed_numbers is None:
                return jsonify({"error": "Định dạng dãy số không hợp lệ"})
            
            logging.info(f"Parsed numbers: {parsed_numbers}")
            return jsonify({
                "count": len(parsed_numbers),
                "numbers": parsed_numbers
            })
        
        elif mode == 'dual':
            sequence1 = request.form.get('sequence1', '')
            sequence2 = request.form.get('sequence2', '')
            logging.info(f"Received sequences: {sequence1}, {sequence2}")
            
            parsed_sequence1 = parse_number_sequence(sequence1)
            parsed_sequence2 = parse_number_sequence(sequence2)
            
            if parsed_sequence1 is None or parsed_sequence2 is None:
                return jsonify({"error": "Định dạng dãy số không hợp lệ"})
            
            is_continuous, message = check_continuity(parsed_sequence1, parsed_sequence2)
            return jsonify({
                "is_continuous": is_continuous,
                "continuity_message": message
            })
        
        return jsonify({"error": "Chế độ không hợp lệ"})
    except Exception as e:
        logging.error(f"Error in calculate route: {str(e)}")
        return jsonify({"error": f"Lỗi xử lý: {str(e)}"})

@app.route('/pdf-analysis')
@login_required
def pdf_analysis():
    return render_template('pdf_analysis.html')

@app.route('/progress')
def progress():
    def generate():
        while not progress_data['complete']:
            # Gửi cập nhật tiến trình mỗi 0.5 giây
            yield f"data: {json.dumps(progress_data)}\n\n"
            time.sleep(0.5)
        # Gửi thông báo hoàn thành cuối cùng
        yield f"data: {json.dumps(progress_data)}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/upload-pdf', methods=['POST'])
def upload_pdf():
    try:
        # Reset tiến trình
        reset_progress()
        
        logging.info("Starting file upload process")
        
        # Đảm bảo thư mục temp tồn tại
        ensure_dir(app.config['UPLOAD_FOLDER'])
        ensure_dir(os.path.join(app.config['UPLOAD_FOLDER'], 'debug'))
        
        if 'file' not in request.files:
            logging.error("No file part in request")
            return jsonify({'error': 'Không tìm thấy file'}), 400
            
        file = request.files['file']
        if file.filename == '':
            logging.error("No selected file")
            return jsonify({'error': 'Chưa chọn file'}), 400
            
        if file and allowed_file(file.filename):
            try:
                # Log thông tin file
                logging.info(f"Processing file: {file.filename}")
                
                # Tạo tên file an toàn với timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_filename = f"{timestamp}_{secure_filename(file.filename)}"
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
                
                # Log đường dẫn đầy đủ
                logging.info(f"Full temp path: {temp_path}")
                
                # Xóa các file cũ
                cleanup_folders()
                
                # Đảm bảo thư mục tồn tại trước khi lưu file
                ensure_dir(os.path.dirname(temp_path))
                
                # Lưu file tạm thời
                file.save(temp_path)
                logging.info(f"File saved to: {temp_path}")
                
                # Kiểm tra file có tồn tại không
                if not os.path.exists(temp_path):
                    logging.error(f"File not found after saving: {temp_path}")
                    return jsonify({'error': 'Lỗi khi lưu file tạm thời'}), 500
                
                # Log file permissions
                logging.info(f"Saved file permissions: {oct(os.stat(temp_path).st_mode)[-3:]}")
                
                # Kiểm tra file PDF có bị mã hóa không
                try:
                    pdf_reader = PyPDF2.PdfReader(temp_path)
                    if pdf_reader.is_encrypted:
                        logging.error("PDF file is encrypted")
                        return jsonify({'error': 'File PDF được bảo vệ bằng mật khẩu. Vui lòng gỡ mật khẩu trước khi tải lên.'}), 400
                    
                    # Cập nhật tổng số trang
                    progress_data['total_pages'] = len(pdf_reader.pages)
                    logging.info(f"PDF has {progress_data['total_pages']} pages")
                    
                except Exception as e:
                    logging.error(f"Error reading PDF: {str(e)}")
                    return jsonify({'error': f'File PDF không hợp lệ hoặc bị hỏng: {str(e)}'}), 400

                # Kiểm tra cài đặt Poppler
                try:
                    check_poppler_installation()
                    logging.info("Poppler installation check passed")
                except RuntimeError as e:
                    logging.error(f"Poppler installation error: {str(e)}")
                    return jsonify({
                        'error': f'Lỗi cài đặt Poppler: {str(e)}. Vui lòng cài đặt lại Poppler theo hướng dẫn.'
                    }), 500
                
                # Đọc PDF và chuyển thành ảnh
                try:
                    logging.info(f"Converting PDF to images: {temp_path}")
                    # Log environment
                    logging.info(f"Platform: {platform.system()}")
                    logging.info(f"POPPLER_PATH: {POPPLER_PATH}")
                    logging.info(f"PATH: {os.environ['PATH']}")
                    
                    # Sử dụng cấu hình khác nhau cho Windows và Linux
                    images = convert_from_path(
                        temp_path,
                        dpi=400,
                        fmt='png',
                        thread_count=4,
                        grayscale=True,
                        size=(2000, None)
                    ) if platform.system() == 'Linux' else convert_from_path(
                        temp_path,
                        poppler_path=POPPLER_PATH,
                        dpi=400,
                        fmt='png',
                        thread_count=4,
                        grayscale=True,
                        size=(2000, None)
                    )
                    logging.info(f"Successfully converted {len(images)} pages")
                    
                    if not images:
                        logging.error("No images extracted from PDF")
                        return jsonify({'error': 'Không thể đọc nội dung file PDF. File có thể rỗng hoặc bị hỏng.'}), 400
                        
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"PDF conversion error: {error_msg}")
                    if "DLL" in error_msg:
                        return jsonify({
                            'error': 'Thiếu file DLL của Poppler. Vui lòng cài đặt lại Poppler và đảm bảo các file DLL được copy đúng vị trí.'
                        }), 500
                    else:
                        return jsonify({
                            'error': f'Lỗi khi chuyển đổi PDF: {error_msg}. '
                                    f'Vui lòng kiểm tra lại file PDF và cài đặt Poppler.'
                        }), 500
                
                # Phân tích từng trang
                pages_info = []
                original_order_numbers = []
                print("\nAnalyzing pages:")
                
                for i, image in enumerate(images):
                    try:
                        print(f"\nProcessing page {i+1}/{len(images)}")
                        
                        # Lưu ảnh gốc để debug
                        debug_path = os.path.join(app.config['UPLOAD_FOLDER'], 'debug')
                        if not os.path.exists(debug_path):
                            os.makedirs(debug_path)
                        image.save(os.path.join(debug_path, f'page_{i+1}.png'))
                        
                        # Trích xuất Order Number
                        order_number = extract_order_number(image)
                        print(f"Found Order Number: {order_number}")
                        
                        if order_number:
                            original_order_numbers.append(order_number)
                            pages_info.append({
                                'original_index': i,
                                'order_number': order_number
                            })
                        
                        # Cập nhật tiến trình
                        progress_data['processed_pages'] = i + 1
                        
                    except Exception as e:
                        print(f"Error processing page {i+1}: {str(e)}")
                        continue
                
                # Đánh dấu hoàn thành
                progress_data['complete'] = True
                
                # Kiểm tra kết quả trích xuất
                if not pages_info:
                    return jsonify({
                        'error': 'Không thể trích xuất Order Number từ bất kỳ trang nào. '
                                'Vui lòng kiểm tra lại định dạng của file PDF hoặc chất lượng hình ảnh.'
                    }), 400
                
                # Sắp xếp trang theo Order Number
                def sort_key(page):
                    if not page['order_number']:
                        return (2, '')  # Trang không có Order Number
                    prefix = page['order_number'][:4]
                    return (
                        0 if prefix == '0900' else 1,  # Ưu tiên 0900
                        page['order_number']
                    )
                
                pages_info.sort(key=sort_key)
                sorted_order_numbers = [page['order_number'] for page in pages_info]
                
                # Tạo PDF mới với thứ tự đã sắp xếp
                print("\nCreating new PDF...")
                pdf_writer = PyPDF2.PdfWriter()
                pdf_reader = PyPDF2.PdfReader(temp_path)
                
                for page in pages_info:
                    try:
                        pdf_writer.add_page(pdf_reader.pages[page['original_index']])
                    except Exception as e:
                        print(f"Error adding page {page['original_index']}: {str(e)}")
                        continue
                
                # Lưu PDF tạm thời
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'sorted_' + safe_filename)
                try:
                    with open(output_path, 'wb') as output_file:
                        pdf_writer.write(output_file)
                    print("PDF created successfully")
                except Exception as e:
                    return jsonify({'error': f'Lỗi khi lưu file PDF: {str(e)}'}), 500
                
                # Lưu thông tin file đã xử lý vào session
                session['processed_file'] = {
                    'original_name': safe_filename,
                    'processed_name': 'sorted_' + safe_filename,
                    'path': output_path,
                    'file_size': os.path.getsize(output_path),
                    'total_pages': progress_data['total_pages'],
                    'processed_pages': progress_data['processed_pages'],
                    'status': 'completed',
                    'order_numbers': sorted_order_numbers
                }
                
                # Lưu thông tin vào database
                save_file_info(session['processed_file'])
                
                return jsonify({
                    'success': True,
                    'message': 'Đã xử lý thành công',
                    'original_order_numbers': original_order_numbers,
                    'sorted_order_numbers': sorted_order_numbers,
                    'total_orders': len(sorted_order_numbers),
                    'output_file': 'sorted_' + safe_filename
                })
                
            except Exception as e:
                print(f"Error during file processing: {str(e)}")
                return jsonify({'error': f'Lỗi xử lý file: {str(e)}'}), 500
                
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({'error': f'Lỗi không xác định: {str(e)}'}), 500

def cleanup_folders():
    """Xóa tất cả file PDF trong thư mục temp và debug"""
    try:
        # Xóa thư mục debug nếu tồn tại
        debug_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'debug')
        if os.path.exists(debug_folder):
            try:
                shutil.rmtree(debug_folder)
                logging.info("Cleaned up debug folder")
            except Exception as e:
                logging.error(f'Error removing debug folder: {e}')

        # Xóa tất cả file PDF trong thư mục temp
        if os.path.exists(app.config['UPLOAD_FOLDER']):
            for filename in os.listdir(app.config['UPLOAD_FOLDER']):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    try:
                        if os.access(file_path, os.W_OK):
                            os.unlink(file_path)
                            logging.info(f"Removed PDF file: {filename}")
                        else:
                            logging.warning(f"No write permission for: {file_path}")
                    except Exception as e:
                        logging.error(f'Error removing {file_path}: {e}')
                        continue
            
    except Exception as e:
        logging.error(f'Error during cleanup: {e}')

@app.route('/download-pdf/<filename>')
def download_pdf(filename):
    try:
        # Kiểm tra xem file đã được xử lý chưa
        if 'processed_file' not in session:
            return jsonify({'error': 'Không tìm thấy file đã xử lý'}), 404
            
        processed_file = session['processed_file']
        if processed_file['processed_name'] != filename:
            return jsonify({'error': 'File không khớp với file đã xử lý'}), 400
            
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'File không tồn tại'}), 404

        # Sao chép file vào thư mục Archive trước khi gửi
        archive_path = os.path.join(app.config['ARCHIVE_FOLDER'], filename)
        try:
            shutil.copy2(file_path, archive_path)
            logging.info(f"File copied to archive: {archive_path}")
        except Exception as e:
            logging.error(f"Error copying file to archive: {str(e)}")
            return jsonify({'error': 'Không thể lưu file vào archive'}), 500
            
        # Thêm headers để force download vào thư mục Downloads
        response = send_from_directory(
            app.config['UPLOAD_FOLDER'],
            filename,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Access-Control-Allow-Origin"] = "*"
        
        # Xóa file khỏi temp sau khi gửi
        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logging.info(f"Removed file from temp after download: {filename}")
                
                # Xóa thông tin file khỏi session
                session.pop('processed_file', None)
            except Exception as e:
                logging.error(f"Error cleaning up after download: {str(e)}")
        
        return response
        
    except Exception as e:
        logging.error(f"Error during download: {str(e)}")
        return jsonify({'error': 'Lỗi khi tải file'}), 500

@app.route('/cleanup-pdf/<filename>')
def cleanup_pdf(filename):
    try:
        cleanup_folders()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
    return jsonify({'success': False})

@app.route('/archive')
@login_required
def archive():
    # Lấy danh sách các file trong thư mục archive
    files = []
    for filename in os.listdir(app.config['ARCHIVE_FOLDER']):
        if filename.endswith('.pdf'):
            file_path = os.path.join(app.config['ARCHIVE_FOLDER'], filename)
            file_stats = os.stat(file_path)
            files.append({
                'name': filename,
                'date': datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'size': f"{file_stats.st_size / 1024:.1f} KB"
            })
    return render_template('archive.html', files=files)

@app.route('/download-archived/<filename>')
def download_archived(filename):
    try:
        return send_from_directory(
            app.config['ARCHIVE_FOLDER'],
            filename,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': 'Không thể tải file'}), 404

def reset_progress():
    global progress_data
    progress_data = {
        'total_pages': 0,
        'processed_pages': 0,
        'complete': False
    }

@app.route('/admin')
@login_required
def admin_dashboard():
    if not is_admin(session['username']):
        return redirect(url_for('home'))
    
    active_users_list = get_active_users()
    return render_template('admin.html', active_users=active_users_list)

@app.route('/admin/force-logout/<username>')
@login_required
def force_logout(username):
    if not is_admin(session['username']):
        return jsonify({'error': 'Không có quyền thực hiện thao tác này'}), 403
    
    if username in active_users:
        del active_users[username]
        return jsonify({'success': True, 'message': f'Đã đăng xuất người dùng {username}'})
    return jsonify({'error': 'Người dùng không tồn tại hoặc đã đăng xuất'}), 404

@app.route('/admin/clear-all')
@login_required
def clear_all_sessions():
    if not is_admin(session['username']):
        return jsonify({'error': 'Không có quyền thực hiện thao tác này'}), 403
    
    active_users.clear()
    return jsonify({'success': True, 'message': 'Đã đăng xuất tất cả người dùng'})

# Cập nhật last_activity cho mỗi request
@app.before_request
def update_last_activity():
    if 'username' in session:
        username = session['username']
        if username in active_users:
            active_users[username]['last_activity'] = datetime.now()

@app.route('/check-file-exists/<filename>')
@login_required
def check_file_exists(filename):
    """Kiểm tra xem file có tồn tại hay không"""
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    exists = os.path.isfile(file_path)
    return jsonify({"exists": exists})

@app.route('/history')
@login_required
def history():
    """Hiển thị lịch sử xử lý file"""
    if not is_admin(session['username']):
        return redirect(url_for('home'))
    files = get_file_history()
    return render_template('history.html', files=files)

def cleanup_old_data():
    """Xóa dữ liệu cũ hơn 24 giờ"""
    try:
        # Lấy thời điểm 24 giờ trước
        cutoff_time = datetime.now() - timedelta(hours=24)
        logging.info(f"Cleaning up data older than: {cutoff_time}")
        
        # 1. Xóa file PDF cũ trong thư mục archive
        if os.path.exists(app.config['ARCHIVE_FOLDER']):
            for filename in os.listdir(app.config['ARCHIVE_FOLDER']):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(app.config['ARCHIVE_FOLDER'], filename)
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    if file_time < cutoff_time:
                        try:
                            os.unlink(file_path)
                            logging.info(f"Removed old archived file: {filename}")
                        except Exception as e:
                            logging.error(f"Error removing old archived file {filename}: {e}")
        
        # 2. Xóa dữ liệu cũ trong database
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Lấy danh sách file cần xóa
        c.execute('''
            SELECT file_path
            FROM files
            WHERE created_at < ?
        ''', (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'),))
        
        old_files = c.fetchall()
        
        # Xóa dữ liệu từ bảng order_numbers
        c.execute('''
            DELETE FROM order_numbers
            WHERE file_id IN (
                SELECT id FROM files
                WHERE created_at < ?
            )
        ''', (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'),))
        
        # Xóa dữ liệu từ bảng files
        c.execute('''
            DELETE FROM files
            WHERE created_at < ?
        ''', (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'),))
        
        conn.commit()
        logging.info(f"Cleaned up {len(old_files)} records from database")
        
    except Exception as e:
        logging.error(f"Error during data cleanup: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

# Khởi tạo scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=cleanup_old_data,
    trigger=IntervalTrigger(hours=1),  # Chạy mỗi giờ để kiểm tra và xóa dữ liệu cũ
    id='cleanup_old_data',
    name='Cleanup old data every hour',
    replace_existing=True
)

# Bắt đầu scheduler
scheduler.start()

# Đảm bảo scheduler được dừng khi ứng dụng tắt
atexit.register(lambda: scheduler.shutdown())

@app.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    """Xóa toàn bộ lịch sử và file trong archive"""
    if not is_admin(session['username']):
        return jsonify({'error': 'Unauthorized access'}), 403
        
    try:
        # 1. Xóa dữ liệu từ database
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        
        # Xóa dữ liệu từ bảng order_numbers
        c.execute('DELETE FROM order_numbers')
        
        # Xóa dữ liệu từ bảng files
        c.execute('DELETE FROM files')
        
        conn.commit()

        # 2. Xóa tất cả file PDF trong thư mục archive
        archive_folder = app.config['ARCHIVE_FOLDER']
        if os.path.exists(archive_folder):
            for filename in os.listdir(archive_folder):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(archive_folder, filename)
                    try:
                        os.unlink(file_path)
                        logging.info(f"Removed archived file: {filename}")
                    except Exception as e:
                        logging.error(f"Error removing archived file {filename}: {e}")
                        continue

        return jsonify({'success': True, 'message': 'Đã xóa toàn bộ lịch sử và file'})
    except Exception as e:
        logging.error(f"Error clearing history: {str(e)}")
        return jsonify({'error': f'Error clearing history: {str(e)}'}), 500
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    app.run(debug=True) 