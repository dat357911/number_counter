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
from datetime import datetime
import time
import json

# Cấu hình đường dẫn
POPPLER_BASE = r'C:\Program Files\poppler-23.11.0'
POPPLER_PATH = os.path.join(POPPLER_BASE, 'Library', 'bin')
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Kiểm tra các file cần thiết
REQUIRED_FILES = [
    'pdftoppm.exe',
    'pdfinfo.exe'
]

# Biến global để theo dõi tiến trình
progress_data = {
    'total_pages': 0,
    'processed_pages': 0,
    'complete': False
}

def check_poppler_installation():
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

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Thay đổi thành một key phức tạp hơn trong production

# Cấu hình cho upload
UPLOAD_FOLDER = 'temp'
DEBUG_FOLDER = os.path.join(UPLOAD_FOLDER, 'debug')
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = None  # Bỏ giới hạn kích thước file

# Thêm cấu hình cho thư mục archive
ARCHIVE_FOLDER = 'archive'
app.config['ARCHIVE_FOLDER'] = ARCHIVE_FOLDER

# Đảm bảo thư mục archive tồn tại
if not os.path.exists(ARCHIVE_FOLDER):
    os.makedirs(ARCHIVE_FOLDER)

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

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/number-analysis')
def number_analysis():
    return render_template('number_analysis.html')

@app.route('/data-analysis')
def data_analysis():
    return render_template('data_analysis.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    mode = request.form.get('mode')
    
    if mode == 'single':
        numbers = request.form.get('numbers', '')
        parsed_numbers = parse_number_sequence(numbers)
        
        if parsed_numbers is None:
            return jsonify({"error": "Định dạng dãy số không hợp lệ"})
        
        return jsonify({
            "count": len(parsed_numbers),
            "numbers": parsed_numbers
        })
    
    elif mode == 'dual':
        sequence1 = request.form.get('sequence1', '')
        sequence2 = request.form.get('sequence2', '')
        
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

@app.route('/pdf-analysis')
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
    # Reset tiến trình
    reset_progress()
    temp_path = None
    
    if 'file' not in request.files:
        return jsonify({'error': 'Không tìm thấy file'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Chưa chọn file'}), 400
        
    if file and allowed_file(file.filename):
        try:
            # Đảm bảo thư mục temp tồn tại
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            
            # Xóa các file cũ trong thư mục temp nếu có
            cleanup_folders()
            
            # Tạo lại thư mục temp nếu cần
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            
            # Lưu file tạm thời
            filename = secure_filename(file.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(temp_path)
            
            # Kiểm tra file PDF có bị mã hóa không
            try:
                pdf_reader = PyPDF2.PdfReader(temp_path)
                if pdf_reader.is_encrypted:
                    return jsonify({'error': 'File PDF được bảo vệ bằng mật khẩu. Vui lòng gỡ mật khẩu trước khi tải lên.'}), 400
                
                # Cập nhật tổng số trang
                progress_data['total_pages'] = len(pdf_reader.pages)
                
            except Exception as e:
                return jsonify({'error': f'File PDF không hợp lệ hoặc bị hỏng: {str(e)}'}), 400

            # Kiểm tra cài đặt Poppler
            try:
                check_poppler_installation()
            except RuntimeError as e:
                return jsonify({
                    'error': f'Lỗi cài đặt Poppler: {str(e)}. Vui lòng cài đặt lại Poppler theo hướng dẫn.'
                }), 500
            
            # Đọc PDF và chuyển thành ảnh với poppler_path
            try:
                print(f"Converting PDF to images: {temp_path}")
                images = convert_from_path(
                    temp_path,
                    poppler_path=POPPLER_PATH,
                    dpi=400,
                    fmt='png',
                    thread_count=4,
                    grayscale=True,
                    size=(2000, None)
                )
                print(f"Successfully converted {len(images)} pages")
                
                if not images:
                    return jsonify({'error': 'Không thể đọc nội dung file PDF. File có thể rỗng hoặc bị hỏng.'}), 400
                    
            except Exception as e:
                error_msg = str(e)
                if "DLL" in error_msg:
                    return jsonify({
                        'error': 'Thiếu file DLL của Poppler. Vui lòng cài đặt lại Poppler và đảm bảo các file DLL được copy đúng vị trí.'
                    }), 500
                else:
                    return jsonify({
                        'error': f'Lỗi khi chuyển đổi PDF: {error_msg}. '
                                f'Vui lòng kiểm tra lại file PDF và cài đặt Poppler tại {POPPLER_PATH}'
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
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'sorted_' + filename)
            try:
                with open(output_path, 'wb') as output_file:
                    pdf_writer.write(output_file)
                print("PDF created successfully")
            except Exception as e:
                return jsonify({'error': f'Lỗi khi lưu file PDF: {str(e)}'}), 500
            
            # Lưu thông tin file đã xử lý vào session
            session['processed_file'] = {
                'original_name': filename,
                'processed_name': 'sorted_' + filename,
                'path': output_path
            }
            
            return jsonify({
                'success': True,
                'message': 'Đã xử lý thành công',
                'original_order_numbers': original_order_numbers,
                'sorted_order_numbers': sorted_order_numbers,
                'total_orders': len(sorted_order_numbers),
                'output_file': 'sorted_' + filename
            })
            
        except Exception as e:
            print(f"Error during processing: {str(e)}")
            return jsonify({'error': f'Lỗi xử lý: {str(e)}'}), 500
            
        finally:
            # Xóa file tạm
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    print(f"Error removing temp file: {str(e)}")
            
    return jsonify({'error': 'File không hợp lệ'}), 400

def cleanup_folders():
    """Xóa hoàn toàn thư mục temp và debug"""
    try:
        # Xóa thư mục debug nếu tồn tại
        if os.path.exists(DEBUG_FOLDER):
            try:
                shutil.rmtree(DEBUG_FOLDER)
            except Exception as e:
                print(f'Error removing debug folder: {e}')

        # Xóa thư mục temp nếu tồn tại
        if os.path.exists(UPLOAD_FOLDER):
            try:
                # Thử xóa từng file trong thư mục temp
                for filename in os.listdir(UPLOAD_FOLDER):
                    file_path = os.path.join(UPLOAD_FOLDER, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        print(f'Error removing {file_path}: {e}')
                        continue
                # Sau khi xóa hết file, thử xóa thư mục temp
                os.rmdir(UPLOAD_FOLDER)
            except Exception as e:
                print(f'Error removing temp folder: {e}')
            
    except Exception as e:
        print(f'Error during cleanup: {e}')

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
        
        return response
        
    except Exception as e:
        print(f"Error during download: {str(e)}")
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

@app.route('/archive-pdf/<filename>')
def archive_pdf(filename):
    try:
        # Kiểm tra xem file đã được xử lý chưa
        if 'processed_file' not in session:
            return jsonify({'error': 'Không tìm thấy file đã xử lý'}), 404
            
        processed_file = session['processed_file']
        if processed_file['processed_name'] != filename:
            return jsonify({'error': 'File không khớp với file đã xử lý'}), 400
            
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        dest_path = os.path.join(app.config['ARCHIVE_FOLDER'], filename)
        
        if not os.path.exists(source_path):
            return jsonify({'error': 'File không tồn tại trong thư mục temp'}), 404
                
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception as e:
                print(f"Error removing existing archive file: {str(e)}")
                return jsonify({'error': 'Không thể xóa file cũ trong archive'}), 500
                
        try:
            shutil.copy2(source_path, dest_path)
            return jsonify({'success': True, 'message': 'File đã được lưu trữ thành công'})
        except Exception as e:
            print(f"Error copying file to archive: {str(e)}")
            return jsonify({'error': 'Không thể copy file vào archive'}), 500
        
    except Exception as e:
        print(f"Error during archiving: {str(e)}")
        return jsonify({'error': str(e)}), 500

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

if __name__ == '__main__':
    app.run(debug=True) 