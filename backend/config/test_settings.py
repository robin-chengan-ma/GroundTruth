from config.settings import *  # noqa: F403

# 測試一律使用固定假金鑰，不依賴也不輸出本機 .env 的真實設定。
SECRET_KEY = "groundtruth-test-secret-key-at-least-32-bytes"
