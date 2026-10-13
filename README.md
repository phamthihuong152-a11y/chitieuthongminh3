# Chi Tiêu Thông Minh

Website quản lý thu chi cá nhân — **backend + SQLite thật**, không dùng localStorage.

## Yêu cầu

- Python 3.8+ (chỉ dùng thư viện chuẩn: `sqlite3`, `http.server`)
- Không cần `npm install` hay pip package

## Cấu trúc

```
chi-tieu-thong-minh/
├── server.py           # Backend HTTP + REST API
├── data/
│   └── chi_tieu.db     # SQLite database (đã seed dữ liệu mẫu)
├── public/
│   └── index.html      # Frontend — gọi API qua fetch()
├── schema.sql          # Lược đồ bảng (khớp với DB và API)
└── README.md
```

## Cách chạy

```bash
cd chi-tieu-thong-minh
python3 server.py
```

Mở trình duyệt: **http://localhost:3000**

Kiểm tra API: **http://localhost:3000/api/health**

## API endpoints

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/api/health` | Trạng thái server + DB |
| GET | `/api/categories` | Danh sách danh mục |
| POST | `/api/categories` | Thêm danh mục `{name, type}` |
| DELETE | `/api/categories/:id` | Xóa danh mục |
| GET | `/api/transactions` | Lọc: `type`, `category_id`, `month`, `year`, `keyword`, `from`, `to` |
| POST | `/api/transactions` | Thêm `{type, amount, date, category_id, note}` |
| PUT | `/api/transactions/:id` | Sửa giao dịch |
| DELETE | `/api/transactions/:id` | Xóa giao dịch |
| GET | `/api/budgets` | Lọc: `month`, `year` |
| POST | `/api/budgets` | Thêm `{month, year, category_id, limit_amount}` |
| PUT | `/api/budgets/:id` | Sửa ngân sách |
| DELETE | `/api/budgets/:id` | Xóa ngân sách |
| GET | `/api/summary` | Tổng thu/chi/số dư theo `month`, `year` |

## Tên trường (thống nhất)

| Bảng | Trường |
|------|--------|
| transactions | `id`, `type`, `amount`, `date`, `category_id`, `note`, `created_at` |
| categories | `id`, `name`, `type` |
| budgets | `id`, `month`, `year`, `category_id`, `limit_amount` |

## Dữ liệu mẫu

- Thu: 17.000.000 ₫ (lương + thưởng)
- Chi: 5.650.000 ₫
- 10 danh mục, 10 giao dịch, 3 ngân sách (tháng 10/2026)

## Lưu ý

- Frontend **không** dùng `localStorage` cho dữ liệu nghiệp vụ.
- Mọi CRUD đi qua API → ghi vào file `data/chi_tieu.db`.
- Reload trang vẫn còn dữ liệu vì đã lưu trong SQLite.
