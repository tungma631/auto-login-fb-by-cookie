# Facebook cookie login cho GPM Login

Script đọc `infor.csv`, ghép cột `Tên profile` với profile GPM theo **đúng tên**, mở profile qua Local API, rồi đưa nguyên chuỗi `Infor` vào extension **Get Token Cookie**. Script không trích xuất hoặc ghi cookie ra log.

## Chuẩn bị

1. Mở và đăng nhập ứng dụng GPM Login. Local API mặc định là `http://127.0.0.1:9495/api/v1`.
2. Thêm thư mục `get-token-cookie-extension` vào GPM và bật extension cho các profile cần chạy.
3. CSV phải có hai cột `Tên profile` và `Infor`. Tên phải trùng hoàn toàn với profile trong GPM.
4. Cài thư viện:

```powershell
python -m pip install -r requirements.txt
```

## Chạy

Kiểm tra ghép dữ liệu trước, chưa mở profile và chưa import cookie:

```powershell
python facebook_cookie_login.py --dry-run
```

Chạy toàn bộ:

```powershell
python facebook_cookie_login.py
```

Chạy thử một profile:

```powershell
python facebook_cookie_login.py --profile "clone 140726 1"
```

Mặc định browser profile được giữ mở. Thêm `--stop-after` nếu muốn GPM đóng từng profile sau khi kiểm tra. Nếu GPM dùng cổng khác:

```powershell
python facebook_cookie_login.py --api http://127.0.0.1:PORT/api/v1
```

Mỗi profile cần tên duy nhất. Kết quả `FAIL` với `checkpoint` hoặc trang login thường có nghĩa cookie đã hết hạn hoặc Facebook yêu cầu xác minh.
