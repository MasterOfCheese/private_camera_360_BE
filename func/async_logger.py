import os
import threading
import queue
from datetime import datetime, timedelta
import time # Cần thêm time để sleep nếu cần, hoặc dùng timeout của queue là đủ
import atexit

class AsyncLogger:
    def __init__(self, log_dir="logs", buffer_size=10, time_interval=5.0): # Thêm time_interval (giây)
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_queue = queue.Queue()
        self.buffer_size = buffer_size
        self.time_interval = timedelta(seconds=time_interval) # Lưu dưới dạng timedelta
        self.buffer = []
        self.last_flush_time = datetime.now() # Lưu thời điểm flush cuối
        self.stop_event = threading.Event()

        self.log_thread = threading.Thread(target=self._process_logs, daemon=True)
        self.log_thread.start()

        # Cân nhắc sử dụng atexit nếu cần đảm bảo stop được gọi khi chương trình thoát đột ngột
        # atexit.register(self.stop)

    def log(self, message, log_level=1, show=True):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] # Thêm milliseconds
        log_message = f"[{timestamp}] [{log_level}] {message}"

        if show:
            print(log_message)

        # Đưa cả datetime object vào queue để _flush dùng cho việc tạo thư mục/file
        self.log_queue.put((log_message, now, log_level))

    def _process_logs(self):
        while not self.stop_event.is_set() or not self.log_queue.empty():
            log_item = None
            try:
                # Sử dụng timeout nhỏ hơn để kiểm tra điều kiện thường xuyên hơn
                # Hoặc giữ timeout=1 và kiểm tra thời gian sau đó
                timeout_check = 1.0 # Giây
                log_item = self.log_queue.get(timeout=timeout_check)
                self.buffer.append(log_item)
                # Lấy xong thì không cần kiểm tra điều kiện thời gian ngay, chờ vòng lặp sau
                # hoặc kiểm tra luôn nếu muốn flush ngay khi có log mới và đủ điều kiện
            except queue.Empty:
                # Queue rỗng, đây là lúc tốt để kiểm tra điều kiện thời gian
                # nếu buffer có dữ liệu
                pass # Không cần làm gì nếu queue rỗng, chỉ cần đi tiếp để check flush

            # --- Điều kiện Flush ---
            should_flush = False
            now = datetime.now()

            # 1. Buffer đầy?
            if len(self.buffer) >= self.buffer_size:
                should_flush = True
                # print(f"DEBUG: Flushing due to buffer size ({len(self.buffer)})") # Debug

            # 2. Hết thời gian VÀ buffer có dữ liệu?
            # Chỉ flush theo thời gian nếu có gì đó trong buffer
            if not should_flush and self.buffer and (now - self.last_flush_time >= self.time_interval):
                 should_flush = True
                 # print(f"DEBUG: Flushing due to time interval ({now - self.last_flush_time})") # Debug

            # Thực hiện flush nếu cần
            if should_flush:
                self._flush()
            # --- Kết thúc điều kiện Flush ---

        # Flush lần cuối trước khi thoát hẳn
        # print("DEBUG: Flushing remaining logs before exit...") # Debug
        self._flush()

    def _flush(self):
        if not self.buffer:
            return # Không có gì để flush

        # print(f"DEBUG: Flushing {len(self.buffer)} items...") # Debug
        logs_by_file = {}
        # Sao chép buffer để xử lý, tránh race condition nếu có (dù ở đây ít khả năng)
        items_to_flush = list(self.buffer)
        self.buffer.clear() # Xóa buffer ngay lập tức (Reset điều kiện size)
        self.last_flush_time = datetime.now() # Reset điều kiện thời gian

        for log_message, dt_obj, log_level in items_to_flush:
            # Sử dụng dt_obj (datetime object) đã lưu từ hàm log
            log_dir_path = os.path.join(self.log_dir, dt_obj.strftime("%Y/%m"))
            os.makedirs(log_dir_path, exist_ok=True)

            log_file_path = os.path.join(log_dir_path, f"{dt_obj.strftime('%d')}_{log_level}.log")

            if log_file_path not in logs_by_file:
                logs_by_file[log_file_path] = []

            logs_by_file[log_file_path].append(log_message)

        for log_file, messages in logs_by_file.items():
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(messages) + "\n")
            except Exception as e:
                # Nên có xử lý lỗi ở đây, ví dụ in ra stderr
                print(f"Error writing to log file {log_file}: {e}", file=sys.stderr)


    def stop(self):
        print('Signaling logger thread to stop...')
        self.stop_event.set()
        # print('Waiting for logger thread to join...') # Debug
        self.log_thread.join() # Đợi luồng xử lý xong
        print('Logger stopped.')

# Ví dụ sử dụng
if __name__ == '__main__':
    import time
    import sys # Để in lỗi ra stderr trong _flush nếu cần

    # Test với buffer nhỏ và interval ngắn
    logger = AsyncLogger(buffer_size=5, time_interval=2) # Flush sau 2 giây hoặc 5 log

    print("Logging 3 items...")
    for i in range(3):
        logger.log(f"Sự kiện số {i}", show=True)
        time.sleep(0.1) # Giả lập log đến từ từ

    print("\nWaiting for time interval flush (should happen after ~2s)...")
    time.sleep(2.5) # Chờ hơn 2 giây

    print("\nLogging 7 more items (will trigger size flush)...")
    for i in range(3, 10):
        logger.log(f"Sự kiện số {i}", show=True)
        # time.sleep(0.1) # Log nhanh để buffer đầy

    print("\nWaiting a bit...")
    time.sleep(1)

    print("\nLogging 2 more items...")
    logger.log("Sự kiện cuối 1", show=True)
    logger.log("Sự kiện cuối 2", show=True)

    print("\nCalling logger.stop()...")
    logger.stop()
    print("Program finished.")