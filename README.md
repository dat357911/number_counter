# Number Counter Web App

Ứng dụng web đếm số lượng số từ dãy số được nhập vào.

## Cách sử dụng
1. Nhập dãy số theo định dạng: 1-10, 12, 15, 19-23
2. Nhấn nút "Tính"
3. Xem kết quả tổng số lượng số và danh sách các số

## Cài đặt
```bash
pip install -r requirements.txt
python app.py
```
```

### Bước 2.4: Upload code lên GitHub
1. Mở Command Prompt trên máy tính của bạn
2. Di chuyển đến thư mục dự án:
```bash
cd đường_dẫn_đến_thư_mục_number_counter
```

3. Khởi tạo Git repository:
```bash
git init
```

4. Thêm các file vào Git:
```bash
git add .
```

5. Commit các thay đổi:
```bash
git commit -m "Initial commit"
```

6. Kết nối với repository trên GitHub:
```bash
git remote add origin https://github.com/yourusername/number_counter.git
```
(Thay `yourusername` bằng username GitHub của bạn)

7. Push code lên GitHub:
```bash
git push -u origin main
```
(Nếu branch chính là "master" thay vì "main", hãy dùng lệnh: `git push -u origin master`)

### Bước 2.5: Kiểm tra
1. Truy cập repository của bạn trên GitHub
2. Kiểm tra xem tất cả các file đã được upload chưa:
   - `app.py`
   - `requirements.txt`
   - `templates/index.html`
   - `.gitignore`
   - `README.md`

### Xử lý lỗi thường gặp:

1. Nếu gặp lỗi "git is not recognized":
   - Tải và cài đặt Git từ: https://git-scm.com/downloads
   - Khởi động lại Command Prompt

2. Nếu gặp lỗi khi push:
   - Kiểm tra xem bạn đã đăng nhập GitHub chưa
   - Thử sử dụng GitHub Desktop thay vì command line

3. Nếu gặp lỗi "remote origin already exists":
   - Chạy lệnh: `git remote remove origin`
   - Sau đó thử lại bước 6

4. Nếu gặp lỗi "main branch does not exist":
   - Chạy lệnh: `git branch -M main`
   - Sau đó thử lại bước 7

Bạn có thể cho tôi biết bạn gặp khó khăn ở bước nào không? Tôi sẽ giúp bạn giải quyết vấn đề đó.
