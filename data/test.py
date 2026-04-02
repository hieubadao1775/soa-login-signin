import sqlite3
from pprint import pprint

conn = sqlite3.connect('account.db')
cursor = conn.cursor()

# Truy vấn toàn bộ dữ liệu từ bảng 'users'
cursor.execute("SELECT * FROM users")

# Lấy tất cả các dòng và in ra
rows = cursor.fetchall()
for row in rows:
    pprint(row)

cursor.execute("DELETE FROM users")
conn.commit()
conn.close()