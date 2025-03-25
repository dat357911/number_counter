from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

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

if __name__ == '__main__':
    app.run(debug=True) 