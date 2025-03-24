from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

def count_numbers(input_text):
    if not input_text:
        return {"error": "Vui lòng nhập dãy số!"}
        
    try:
        numbers = set()
        # Tách các phần tử bằng dấu phẩy
        parts = [part.strip() for part in input_text.split(",")]
        
        for part in parts:
            if "-" in part:
                # Xử lý khoảng số (ví dụ: 1-10)
                start, end = map(int, part.split("-"))
                numbers.update(range(start, end + 1))
            else:
                # Xử lý số đơn lẻ
                numbers.add(int(part))
        
        return {"count": len(numbers), "numbers": sorted(list(numbers))}
        
    except ValueError:
        return {"error": "Định dạng không hợp lệ! Vui lòng kiểm tra lại."}
    except Exception as e:
        return {"error": f"Có lỗi xảy ra: {str(e)}"}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    input_text = request.form.get('numbers', '').strip()
    result = count_numbers(input_text)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 