#!/usr/bin/env python3
"""
KPI ダッシュボードをスクリーンショットして Gmail でメール送信するスクリプト

前提:
    pip install playwright requests
    playwright install chromium

環境変数:
    GMAIL_USER   : 送信元 Gmail アドレス
    GMAIL_PASS   : Gmail アプリパスワード（16桁）
    REPORT_TO    : 送信先メールアドレス（複数の場合はカンマ区切り）
    SURGE_DOMAIN : surge.sh のドメイン名（例: diagram-dashboard-poc.surge.sh）
                   省略時はスクリーンショットのみ添付（URLリンクなし）
"""

import os
import smtplib
import sys
import tempfile
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

GMAIL_USER   = os.environ.get("GMAIL_USER", "").strip()
GMAIL_PASS   = os.environ.get("GMAIL_PASS", "").strip()
REPORT_TO    = os.environ.get("REPORT_TO", "").strip()
SURGE_DOMAIN = os.environ.get("SURGE_DOMAIN", "").strip()

OVERVIEW_HTML    = "output/dashboard-overview.html"
INDIVIDUAL_HTML  = "output/dashboard-individual.html"


# ====================================================================
# スクリーンショット取得
# ====================================================================

def screenshot(html_path: str, out_path: str, width: int = 1000,
               clip_marker_id: str | None = None, hide_email_elements: bool = False) -> bool:
    """Playwright で HTML をスクリーンショット撮影。
    clip_marker_id を指定すると、そのIDを持つ要素の底辺までをクリップする。
    hide_email_elements=True にすると data-email-hide="true" の要素を非表示にしてから全ページ撮影する。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright が必要です。pip install playwright && playwright install chromium を実行してください。")
        return False

    abs_path = str(Path(html_path).resolve())
    file_url = f"file://{abs_path}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page    = browser.new_page(viewport={"width": width, "height": 1200})
        page.goto(file_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)  # フォント・アイコン読み込み待機

        if hide_email_elements:
            page.evaluate("document.querySelectorAll('[data-email-hide]').forEach(el => el.style.display = 'none')")

        if clip_marker_id:
            el = page.locator(f"#{clip_marker_id}").first
            box = el.bounding_box()
            if box:
                clip_height = int(box["y"] + box["height"] + 40)  # 余白40px
                page.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": width, "height": clip_height})
            else:
                page.screenshot(path=out_path, full_page=True)
        else:
            page.screenshot(path=out_path, full_page=True)
        browser.close()

    print(f"  スクリーンショット: {out_path}")
    return True


# ====================================================================
# メール送信
# ====================================================================

def send(overview_png: str | None, individual_png: str | None):
    """Gmail SMTP でレポートメールを送信"""
    if not GMAIL_USER:
        print("ERROR: 環境変数 GMAIL_USER が設定されていません。")
        sys.exit(1)
    if not GMAIL_PASS:
        print("ERROR: 環境変数 GMAIL_PASS が設定されていません（アプリパスワード16桁）。")
        sys.exit(1)
    if not REPORT_TO:
        print("ERROR: 環境変数 REPORT_TO が設定されていません。")
        sys.exit(1)

    recipients = [r.strip() for r in REPORT_TO.split(",") if r.strip()]

    # ---- 本文 HTML ----
    overview_url    = f"https://{SURGE_DOMAIN}/dashboard-overview.html"    if SURGE_DOMAIN else ""
    individual_url  = f"https://{SURGE_DOMAIN}/dashboard-individual.html"  if SURGE_DOMAIN else ""

    url_section = ""
    if SURGE_DOMAIN:
        url_section = f"""
<p style="margin:0 0 8px;">
  <a href="{overview_url}"    style="color:#ff4e00;font-weight:bold;">&#128202; 支社別ビュー（ブラウザで開く）</a><br>
  <a href="{individual_url}"  style="color:#ff4e00;font-weight:bold;">&#128100; 個人別ビュー（ブラウザで開く）</a>
</p>"""

    screenshot_section_ov  = '<img src="cid:overview_img"    style="width:100%;border-radius:8px;margin-bottom:16px;" alt="支社別ビュー">'    if overview_png    else ""
    screenshot_section_ind = '<img src="cid:individual_img"  style="width:100%;border-radius:8px;margin-bottom:16px;" alt="個人別ビュー">'    if individual_png  else ""

    body_html = f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Noto Sans JP',sans-serif;background:#f1efe7;margin:0;padding:20px;">
<div style="max-width:680px;margin:0 auto;background:#fff;border-radius:12px;border-top:4px solid #ff4e00;padding:24px;">
  <p style="color:#ff4e00;font-size:11px;font-weight:bold;letter-spacing:0.1em;margin:0 0 4px;">生産性レポート</p>
  <h1 style="font-size:22px;font-weight:900;color:#343430;margin:0 0 8px;">本日の生産性ダッシュボード</h1>
  <p style="font-size:13px;color:#666460;margin:0 0 20px;">支社・個人の生産性を自動集計しました。</p>
  {url_section}
  <hr style="border:none;border-top:1px solid #e5e2d9;margin:20px 0;">
  <p style="font-size:12px;font-weight:bold;color:#9a9690;margin:0 0 12px;">支社別ビュー</p>
  {screenshot_section_ov}
  <p style="font-size:12px;font-weight:bold;color:#9a9690;margin:0 0 12px;">個人別ビュー</p>
  {screenshot_section_ind}
  <hr style="border:none;border-top:1px solid #e5e2d9;margin:20px 0;">
  <p style="font-size:11px;color:#9a9690;margin:0;">このメールは GitHub Actions によって自動送信されています。</p>
</div>
</body>
</html>"""

    # ---- MIMEメッセージ組み立て ----
    msg = MIMEMultipart("related")
    msg["Subject"] = "【生産性レポート】本日のダッシュボード"
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("生産性ダッシュボードのレポートが届きました。HTMLメール対応のメーラーでご確認ください。", "plain", "utf-8"))
    alt.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(alt)

    # 画像添付
    if overview_png and os.path.exists(overview_png):
        with open(overview_png, "rb") as f:
            img = MIMEImage(f.read(), _subtype="png")
            img.add_header("Content-ID", "<overview_img>")
            img.add_header("Content-Disposition", "inline", filename="overview.png")
            msg.attach(img)

    if individual_png and os.path.exists(individual_png):
        with open(individual_png, "rb") as f:
            img = MIMEImage(f.read(), _subtype="png")
            img.add_header("Content-ID", "<individual_img>")
            img.add_header("Content-Disposition", "inline", filename="individual.png")
            msg.attach(img)

    # ---- Gmail SMTP 送信 ----
    print(f"メール送信中: {', '.join(recipients)}")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_PASS)
        smtp.sendmail(GMAIL_USER, recipients, msg.as_bytes())

    print(f"✓ 送信完了: {len(recipients)} 件")


# ====================================================================
# エントリーポイント
# ====================================================================

def main():
    print("=== send-report.py 開始 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        ov_png  = os.path.join(tmpdir, "overview.png")
        ind_png = os.path.join(tmpdir, "individual.png")

        # スクリーンショット取得（失敗しても送信は続行）
        ov_ok  = False
        ind_ok = False

        if os.path.exists(OVERVIEW_HTML):
            # KPIカード〜支社別ランキング（生産性グラフ）までをキャプチャ
            ov_ok = screenshot(OVERVIEW_HTML, ov_png, clip_marker_id="overview-clip-end")
        else:
            print(f"WARNING: {OVERVIEW_HTML} が見つかりません。スクリーンショットをスキップします。")

        if os.path.exists(INDIVIDUAL_HTML):
            # 個人別ビュー：ランキング棒グラフのみ（テーブル・コメント・トレンドは非表示）で全局分
            ind_ok = screenshot(INDIVIDUAL_HTML, ind_png, hide_email_elements=True)
        else:
            print(f"WARNING: {INDIVIDUAL_HTML} が見つかりません。スクリーンショットをスキップします。")

        send(
            overview_png    = ov_png  if ov_ok  else None,
            individual_png  = ind_png if ind_ok else None,
        )

    print("=== send-report.py 完了 ===")


if __name__ == "__main__":
    main()
