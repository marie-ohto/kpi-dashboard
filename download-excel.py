#!/usr/bin/env python3
import os
import sys

try:
    import requests
except ImportError:
    print("ERROR: requests が必要です。")
    sys.exit(1)

FILE_ID = os.environ.get("GDRIVE_FILE_ID", "").strip()
OUTPUT  = "data.xlsx"

def download():
    if not FILE_ID:
        print("ERROR: 環境変数 GDRIVE_FILE_ID が設定されていません。")
        sys.exit(1)

    # Google スプレッドシートは export URL を使う
    url = f"https://docs.google.com/spreadsheets/d/{FILE_ID}/export?format=xlsx"
    print(f"ダウンロード中: file_id={FILE_ID}")

    response = requests.get(url, stream=True, timeout=60)

    if response.status_code != 200:
        print(f"ERROR: ダウンロード失敗（HTTP {response.status_code}）")
        sys.exit(1)

    with open(OUTPUT, "wb") as f:
        for chunk in response.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)

    print(f"✓ ダウンロード完了: {OUTPUT}")

if __name__ == "__main__":
    download()
