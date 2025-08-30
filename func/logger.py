# deprecated
import os
from datetime import datetime

class Logger:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    def log(self, message, log_level=1, save=True, show=True):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{log_level}] {message}"

        # In ra console nếu cần
        if show:
            print(log_message)

        # Lưu vào file nếu cần
        if save:
            log_dir = os.path.join(self.log_dir, now.strftime("%Y/%m"))
            os.makedirs(log_dir, exist_ok=True)

            log_file_path = os.path.join(log_dir, f"{now.strftime('%d')}_{log_level}.log")

            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")


if __name__ == '__main__':
    # Ví dụ sử dụng
    logger = Logger()
    logger.log("Bắt đầu chương trình.")
    logger.log("Đã xử lý xong dữ liệu.")
    logger.log("Kết thúc chương trình.")