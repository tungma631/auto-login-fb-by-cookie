# Chạy tool trên máy Windows khác

## Sao chép

Nén và chép nguyên thư mục này sang máy mới. Tối thiểu phải có:

- `facebook_cookie_login.py`
- `requirements.txt`
- `infor.csv`
- thư mục `get-token-cookie-extension`
- `CHAY_TOOL.bat`

Không chỉ chép riêng file Python vì tool còn cần CSV và extension.

## Chuẩn bị máy mới

1. Cài Python 3 từ python.org và bật `Add Python to PATH` khi cài.
2. Cài, đăng nhập và mở GPM Login.
3. Tạo hoặc đồng bộ các profile GPM. Tên profile phải trùng cột `Tên profile` trong CSV.
4. Đóng `infor.csv` trong Excel trước khi chạy để tool ghi được `Status`.

## Chạy

Nhấp đúp `CHAY_TOOL.bat`. File này tự cài Selenium rồi chạy tool.

Hoặc dùng PowerShell trong thư mục tool:

```powershell
python -m pip install -r requirements.txt
python facebook_cookie_login.py --csv infor.csv
```

Tool tự dò API theo thứ tự: `--api`, biến môi trường, file `http.port`, cổng GPM mặc định.

Nếu vẫn không tự dò được, nhập URL hiển thị trong phần API của GPM:

```powershell
python facebook_cookie_login.py --csv infor.csv --api http://127.0.0.1:9495/api/v1
```

Cũng có thể chỉ truyền cổng:

```powershell
python facebook_cookie_login.py --csv infor.csv --api 9495
```

Hoặc lưu cấu hình riêng của máy trong biến môi trường:

```powershell
setx GPM_API_PORT 9495
```

Sau khi mở lại PowerShell, tool sẽ tự dùng cổng đó. Có thể dùng `GPM_API_URL` thay cho `GPM_API_PORT` nếu cần chỉ định đầy đủ URL.

## Kiểm tra trước

```powershell
python facebook_cookie_login.py --csv infor.csv --dry-run
```

Các dòng có `Status = done` được bỏ qua. Profile thành công được ghi `done` ngay sau khi hoàn tất.
