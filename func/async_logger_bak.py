import os
import threading
import queue
from datetime import datetime
import atexit

class AsyncLogger:
    def __init__(self, log_dir="logs", buffer_size=10):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.log_queue = queue.Queue()
        self.buffer_size = buffer_size
        self.buffer = []
        self.stop_event = threading.Event()
        
        self.log_thread = threading.Thread(target=self._process_logs, daemon=True)
        self.log_thread.start()
        
        # atexit.register(self.stop)

    def log(self, message, log_level=1, show=True):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{log_level}] {message}"

        if show:
            print(log_message)

        self.log_queue.put((log_message, now, log_level))

    def _process_logs(self):
        while not self.stop_event.is_set() or not self.log_queue.empty():
            try:
                log_message, now, log_level = self.log_queue.get(timeout=1)
                self.buffer.append((log_message, now, log_level))

                if len(self.buffer) >= self.buffer_size:
                    self._flush()
            except queue.Empty:
                continue

        self._flush()  # Flush remaining logs before exit

    def _flush(self):
        if not self.buffer:
            return

        logs_by_file = {}
        for log_message, now, log_level in self.buffer:
            log_dir = os.path.join(self.log_dir, now.strftime("%Y/%m"))
            os.makedirs(log_dir, exist_ok=True)

            log_file_path = os.path.join(log_dir, f"{now.strftime('%d')}_{log_level}.log")

            if log_file_path not in logs_by_file:
                logs_by_file[log_file_path] = []

            logs_by_file[log_file_path].append(log_message)

        for log_file, messages in logs_by_file.items():
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("\n".join(messages) + "\n")

        self.buffer.clear()

    def stop(self):
        self.stop_event.set()
        self.log_thread.join()
        print('Stopping logger...')

if __name__ == '__main__':
    logger = AsyncLogger()

    for i in range(50):
        logger.log(f"Sự kiện số {i}")

    logger.stop()
