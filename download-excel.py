#!/usr/bin/env python3
"""
Google Drive から Excel ファイルをダウンロードするスクリプト

環境変数:
    GDRIVE_FILE_ID : Google Drive のファイルID（共有URLの /d/〇〇〇/ の部分）
    GDRIVE_API_KEY : Google Drive API キー（省略可。省略時は公開共有リンクとして取得）

出力:
    data.xlsx
"""

import os
import sys

try:
    import requests
except ImportError:
    print("ERROR: requests が必要です。pip install requests で導入してください。")
    sys.exit(1)

FILE_ID  = os.environ.get("GDRIVE_FILE_ID", "").strip()
API_KEY  = os.environ.get("GDRIVE_API_KEY", "").strip()
OUTPUT   = "data.xlsx"


def download():
    if not FILE_ID:
        print("ERROR: 環境変数 GDRIVE_FILE_ID が設定されていません。")
        print("  GitHub Settings → Secrets → GDRIVE_FILE_ID を登録してください。")
        sys.exit(1)

    session = requests.Session()

    if API_KEY:
        # API キーがある場合: Drive v3 API 経由で取得（非公開ファイルでも可）
        url = f"https://www.googleapis.com/drive/v3/files/{FILE_ID}?alt=media&key={API_KEY}"
        print(f"ダウンロード中（Drive API）: file_id={FILE_ID}")
        response = session.get(url, stream=True, timeout=60)
    else:
        # 公開共有リンク経由で取得
        url = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
        print(f"ダウンロード中（公開リンク）: file_id={FILE_ID}")
        response = session.get(url, stream=True, timeout=60)

        # Google Drive の「大きいファイルの警告」をスキップする
        confirm_token = None
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                confirm_token = value
                break

        if confirm_token:
            params = {"id": FILE_ID, "confirm": confirm_token, "export": "download"}
            response = session.get("https://drive.google.com/uc", params=params, stream=True, timeout=60)

    if response.status_code != 200:
        print(f"ERROR: ダウンロードに失敗しました（HTTP {response.status_code}）。")
        print("  Google Drive の共有設定が「リンクを知っている全員」になっているか確認してください。")
        sys.exit(1)

    with open(OUTPUT, "wb") as f:
        for chunk in response.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)

    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"✓ ダウンロード完了: {OUTPUT}（{size_kb:.1f} KB）")


if __name__ == "__main__":
    download()
