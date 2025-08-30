import sys
import yaml
import os

class Config:
    def __init__(self, config_path="config.yaml"):
        self.config_path = config_path
        self.config = {}
    # def default_config(self):
    #     self.set_config(host='0.0.0.0', port=8000, log_dir = 'logs', token_expiry_minutes=1440, db_connection_string='postgresql+asyncpg://postgres:root@localhost:5432/thai_test')
    def default_config(self):
        self.set_config(host='0.0.0.0', port=8000, log_dir = 'logs', token_expiry_minutes=1440, db_connection_string='postgresql+asyncpg://postgres:root@localhost:5432/thai_test')
    def load_config(self):
        try:
            with open(self.config_path, 'r') as file:
                self.config = yaml.safe_load(file) or {}
            print(f"Đã tải cấu hình từ {self.config_path}")
        except FileNotFoundError:
            print(f"Không tìm thấy file cấu hình tại {self.config_path}. Tạo file mới.")
            self.default_config()
            self.save_config()
            sys.exit(1)
            
        except yaml.YAMLError as e:
            print(f"Lỗi khi tải file cấu hình: {e}")
            print("Đang tạo file cấu hình mặc định.")
            self.default_config()
            self.save_config()
            sys.exit(1)
            
        except Exception as e:
            print(f"Lỗi không xác định khi tải file cấu hình: {e}")
            print("Đang tạo file cấu hình mặc định.")
            self.default_config()
            self.save_config()
            sys.exit(1)

    def save_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as file:
            yaml.dump(self.config, file)
        print(f"Đã lưu cấu hình vào {self.config_path}")

    def get_config(self):
        # return self.config
        return ConfigObject(**self.config)

    def set_config(self, **kwargs):
        self.config.update(kwargs)
        self.save_config()
class ConfigObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self):
        return str(self.__dict__)

    def to_dict(self):
        return self.__dict__
# Ví dụ sử dụng
if __name__ == "__main__":
    config_manager = Config("configs/my_config.yaml")

    config_manager.load_config()
    a = config_manager.get_config()
    print("Cấu hình hiện tại:", a)
    print(a.runtime.test1)

    # Thay đổi cấu hình bằng keyword arguments
    # config_manager.set_config(database={"host": "new_host", "port": 5433}, api_key="new_api_key", timeout=10)
    # pass
    # config_manager.save_config()

    # print("Cấu hình sau khi cập nhật:", config_manager.get_config())