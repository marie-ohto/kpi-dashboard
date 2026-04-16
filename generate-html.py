#!/usr/bin/env python3
"""
metrics.json から KPI ダッシュボード HTML を生成するスクリプト

Usage:
    python3 generate-html.py metrics.json [--output-dir output]

Output:
    {output_dir}/dashboard-overview.html   支社別ビュー
    {output_dir}/dashboard-individual.html 個人別ビュー
    {output_dir}/index.html                overview へのリダイレクト
"""

import argparse
import json
import os
import sys
from datetime import datetime

# ====================================================================
# カラー定義（design-system.md 準拠）
# ====================================================================
RANK_COLORS = ["#059669", "#343430", "#666460", "#9a9690"]
LAST_COLOR  = "#ff4e00"


def rank_color(i: int, n: int) -> str:
    if i == 0:
        return RANK_COLORS[0]
    if i == n - 1:
        return LAST_COLOR
    if i < len(RANK_COLORS):
        return RANK_COLORS[i]
    return "#9a9690"


def badge_style(ratio_pct: int, is_last: bool) -> str:
    if ratio_pct >= 100:
        return "background:#059669;color:#fff;"
    if ratio_pct >= 90:
        return "background:#f7f5ef;color:#666460;border:1px solid #e5e2d9;"
    if is_last:
        return "background:#ff4e00;color:#fff;"
    return "background:#fff0eb;color:#ff4e00;border:1px solid #ffd0bb;"


def badge_text(ratio_pct: int) -> str:
    if ratio_pct >= 100:
        return "達成"
    if ratio_pct >= 90:
        return "要注意"
    return "未達成"


def format_date(d: str) -> str:
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return f"{dt.year}/{dt.month}/{dt.day}"
    except Exception:
        return d


# ====================================================================
# SVG チャート生成
# ====================================================================

def bar_chart_svg(items: list, baseline: float, prod_key="avg_productivity") -> str:
    """横棒ランキングチャートSVGを生成"""
    n = len(items)
    if n == 0:
        return '<svg viewBox="0 0 520 50"></svg>'

    ROW_H     = 42
    BAR_H     = 24
    BAR_START = 120
    BAR_W     = 370

    max_val  = max(item[prod_key] for item in items)
    axis_max = max(max_val * 1.18, baseline * 1.12)
    scale    = BAR_W / axis_max if axis_max > 0 else 1
    bx       = BAR_START + scale * baseline  # 基準線X

    view_h = n * ROW_H + 22
    svg = [f'<svg viewBox="0 0 520 {view_h}" class="w-full mb-5" xmlns="http://www.w3.org/2000/svg">']

    # グリッド線・軸ラベル（0, 25%, 50%, 75%, 100% of axis_max）
    ticks = [axis_max * t / 4 for t in range(5)]
    for tv in ticks:
        tx = BAR_START + scale * tv
        lw = "1" if tv == 0 else "0.5"
        da = "" if tv == 0 else ' stroke-dasharray="3,3"'
        svg.append(f'<line x1="{tx:.0f}" y1="0" x2="{tx:.0f}" y2="{n*ROW_H}" stroke="#e5e2d9" stroke-width="{lw}"{da}/>')
        label = f"{tv:.0f}" if tv < axis_max else f"{tv:.0f}件/h"
        svg.append(f'<text x="{tx:.0f}" y="{n*ROW_H+13}" text-anchor="middle" font-size="9" fill="#9a9690">{label}</text>')

    # 基準線
    svg.append(f'<line x1="{bx:.0f}" y1="0" x2="{bx:.0f}" y2="{n*ROW_H}" stroke="#ff4e00" stroke-width="1.5" stroke-dasharray="5,3"/>')
    svg.append(f'<text x="{bx:.0f}" y="-3" text-anchor="middle" font-size="9" fill="#ff4e00" font-weight="bold">基準{baseline:.0f}</text>')

    # バー
    for i, item in enumerate(items):
        cy       = i * ROW_H + ROW_H // 2
        bar_y    = i * ROW_H + (ROW_H - BAR_H) // 2
        bar_w    = scale * item[prod_key]
        color    = rank_color(i, n)
        pct      = round(item["standard_ratio"] * 100)
        val_x    = BAR_START + bar_w + 5

        # バッジ
        svg.append(f'<circle cx="10" cy="{cy}" r="9" fill="{color}"/>')
        svg.append(f'<text x="10" y="{cy+4}" text-anchor="middle" font-size="9" fill="white" font-weight="bold">{i+1}</text>')

        # ラベル（名前）
        name = item["name"]
        if len(name) > 9:
            name = name[:8] + "…"
        svg.append(f'<text x="25" y="{cy-3}" text-anchor="start" font-size="10.5" fill="#343430" font-weight="600">{name}</text>')

        # バー本体
        svg.append(f'<rect x="{BAR_START}" y="{bar_y}" width="{bar_w:.1f}" height="{BAR_H}" fill="{color}" rx="3"/>')

        # 値ラベル
        ratio_fill = "#ff4e00" if pct < 90 else ("#059669" if pct >= 100 else "#666460")
        ratio_text = f"{pct}%" + (" ▼" if pct < 90 else "")
        bold_attr  = ' font-weight="bold"' if pct < 90 else ""
        svg.append(f'<text x="{val_x:.0f}" y="{cy+1}" font-size="11" fill="#343430" font-weight="700">{item[prod_key]:.1f}件/h</text>')
        svg.append(f'<text x="{val_x:.0f}" y="{cy+13}" font-size="9" fill="{ratio_fill}"{bold_attr}>{ratio_text}</text>')

    svg.append('</svg>')
    return "\n".join(svg)


def line_chart_svg(items: list, all_dates: list, height: int = 180) -> str:
    """折れ線グラフSVGを生成"""
    if not all_dates or not items:
        return f'<svg viewBox="0 0 520 {height}"></svg>'

    X1, X2 = 48, 500
    Y1, Y2 = 15, height - 28
    PW, PH  = X2 - X1, Y2 - Y1
    n_dates = len(all_dates)
    n_items = len(items)

    all_vals = [
        v
        for item in items
        for d in all_dates
        for v in [item["daily_productivity"].get(d)]
        if v is not None
    ]
    if not all_vals:
        return f'<svg viewBox="0 0 520 {height}"></svg>'

    y_min   = max(0.0, min(all_vals) * 0.88)
    y_max   = max(all_vals) * 1.1
    y_range = y_max - y_min if y_max != y_min else 1.0

    def xp(di):
        return X1 if n_dates == 1 else X1 + di / (n_dates - 1) * PW

    def yp(v):
        return Y2 - (v - y_min) / y_range * PH

    svg = [f'<svg viewBox="0 0 520 {height}" class="w-full" xmlns="http://www.w3.org/2000/svg">']

    # Y グリッド
    for t in range(5):
        tv = y_min + (y_max - y_min) * t / 4
        ty = yp(tv)
        svg.append(f'<line x1="{X1}" y1="{ty:.1f}" x2="{X2}" y2="{ty:.1f}" stroke="#e5e2d9" stroke-width="0.5" stroke-dasharray="3,3"/>')
        svg.append(f'<text x="{X1-4}" y="{ty+3:.1f}" text-anchor="end" font-size="9" fill="#9a9690">{tv:.0f}</text>')

    # X 軸ラベル（最大7本）
    step = max(1, n_dates // 7)
    for di, d in enumerate(all_dates):
        if di % step == 0 or di == n_dates - 1:
            label = d[5:] if len(d) == 10 else d
            svg.append(f'<text x="{xp(di):.0f}" y="{Y2+14}" text-anchor="middle" font-size="8.5" fill="#9a9690">{label}</text>')

    # 折れ線
    MID_GRAYS = ["#aaa9a6", "#c0bfbc", "#d4d3d0"]
    for i, item in enumerate(items):
        if i == 0:
            color, sw, da = "#059669", "2", ""
        elif i == n_items - 1:
            color, sw, da = "#ff4e00", "1.5", ' stroke-dasharray="4,2"'
        else:
            gi = (i - 1) % len(MID_GRAYS)
            color, sw, da = MID_GRAYS[gi], "1", ""

        pts = [(xp(di), yp(v)) for di, d in enumerate(all_dates) if (v := item["daily_productivity"].get(d)) is not None]
        if len(pts) < 2:
            continue

        path_d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f} " + " ".join(f"L {px:.1f} {py:.1f}" for px, py in pts[1:])
        svg.append(f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="{sw}"{da}/>')

        # ラベル（最終点の右）
        lx, ly = pts[-1]
        name   = item["name"][:5] + "…" if len(item["name"]) > 5 else item["name"]
        bold   = ' font-weight="bold"' if i in (0, n_items - 1) else ""
        svg.append(f'<text x="{lx+3:.0f}" y="{ly+3:.1f}" font-size="8.5" fill="{color}"{bold}>{name}</text>')

    svg.append('</svg>')
    return "\n".join(svg)


def scatter_svg(bureaus: list, baseline: float, work_hours: float, period_end: str) -> str:
    """人員過不足アラート散布図SVGを生成"""
    X1, X2 = 52, 480
    Y1, Y2 = 15, 155
    PW, PH  = X2 - X1, Y2 - Y1

    threshold = work_hours * baseline
    danger    = (work_hours + 1) * baseline

    pts = []
    for b in bureaus:
        cr = b["daily_completion_rate"].get(period_end)
        if cr is None and b["daily_completion_rate"]:
            cr = list(b["daily_completion_rate"].values())[-1]
        if cr is not None:
            pts.append((b["name"], b["manpower_index_latest"], cr))

    if not pts:
        return '<svg viewBox="0 0 520 180"><text x="260" y="90" text-anchor="middle" fill="#9a9690">データなし</text></svg>'

    x_max = max(p[1] for p in pts) * 1.2
    x_max = max(x_max, danger * 1.1)

    def xp(v):
        return X1 + v / x_max * PW

    def yp(v):
        return Y2 - v * PH  # 0〜1 → Y2〜Y1

    svg = ['<svg viewBox="0 0 520 180" class="w-full" xmlns="http://www.w3.org/2000/svg">']

    # Y グリッド
    for v in (0.25, 0.50, 0.75, 1.00):
        ty = yp(v)
        svg.append(f'<line x1="{X1}" y1="{ty:.1f}" x2="{X2}" y2="{ty:.1f}" stroke="#e5e2d9" stroke-width="0.5" stroke-dasharray="3,3"/>')
        svg.append(f'<text x="{X1-4}" y="{ty+3:.1f}" text-anchor="end" font-size="9" fill="#9a9690">{int(v*100)}%</text>')

    # 閾値線
    tx_thresh = xp(threshold)
    tx_danger = xp(danger)
    svg.append(f'<line x1="{tx_thresh:.0f}" y1="{Y1}" x2="{tx_thresh:.0f}" y2="{Y2}" stroke="#ffd0bb" stroke-width="1.5" stroke-dasharray="4,2"/>')
    svg.append(f'<text x="{tx_thresh:.0f}" y="{Y1-3}" text-anchor="middle" font-size="8" fill="#ff9966">適正 {threshold:.0f}</text>')
    svg.append(f'<line x1="{tx_danger:.0f}" y1="{Y1}" x2="{tx_danger:.0f}" y2="{Y2}" stroke="#ff4e00" stroke-width="1.5" stroke-dasharray="4,2"/>')
    svg.append(f'<text x="{tx_danger:.0f}" y="{Y1-3}" text-anchor="middle" font-size="8" fill="#ff4e00">危険 {danger:.0f}</text>')

    # 軸
    svg.append(f'<line x1="{X1}" y1="{Y2}" x2="{X2}" y2="{Y2}" stroke="#e5e2d9" stroke-width="1"/>')
    svg.append(f'<line x1="{X1}" y1="{Y1}" x2="{X1}" y2="{Y2}" stroke="#e5e2d9" stroke-width="1"/>')
    svg.append(f'<text x="{(X1+X2)//2}" y="175" text-anchor="middle" font-size="9" fill="#9a9690">1人あたり投入量（件）</text>')

    # ドット
    for name, mx, cr in pts:
        px = xp(mx)
        py = yp(cr)
        alert = mx > danger and cr < 0.90
        color = "#ff4e00" if alert else ("#059669" if cr >= 1.0 else "#343430")
        svg.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{color}" opacity="0.85"/>')
        short = name[:4] + "…" if len(name) > 4 else name
        svg.append(f'<text x="{px:.1f}" y="{py-9:.1f}" text-anchor="middle" font-size="8.5" fill="{color}" font-weight="bold">{short}</text>')

    svg.append('</svg>')
    return "\n".join(svg)


# ====================================================================
# テーブル生成
# ====================================================================

def rank_table_html(items: list) -> str:
    """標準比テーブルHTMLを生成"""
    n = len(items)
    rows = []
    for i, item in enumerate(items):
        pct     = round(item["standard_ratio"] * 100)
        is_last = i == n - 1
        color   = rank_color(i, n)

        row_bg = ""
        if pct < 90:
            row_bg = ' style="background:#fff0eb;"' if is_last else ' style="background:#fff8f6;"'

        b_style = badge_style(pct, is_last)
        b_text  = badge_text(pct)

        name_cls = "text-xs font-bold text-ads-accent" if (is_last and pct < 90) else "text-xs font-medium text-ads-text"
        val_cls  = "px-3 py-2.5 text-right text-xs font-bold text-ads-accent" if pct < 90 else "px-3 py-2.5 text-right text-xs font-bold text-ads-text"

        rows.append(f'''
              <tr class="border-b border-ads-border"{row_bg}>
                <td class="px-3 py-2.5">
                  <div class="flex items-center gap-2">
                    <div class="w-2 h-2 rounded-full shrink-0" style="background:{color};"></div>
                    <span class="{name_cls}">{item["name"]}</span>
                  </div>
                </td>
                <td class="{val_cls}" style="font-family:'Inter',sans-serif;">{item["avg_productivity"]:.1f} 件/h</td>
                <td class="{val_cls}">{pct}%</td>
                <td class="px-3 py-2.5 text-center">
                  <span class="text-xs px-2 py-0.5 rounded-full font-bold" style="{b_style}">{b_text}</span>
                </td>
              </tr>''')

    return f'''
        <div class="border border-ads-border rounded-xl overflow-hidden mb-4">
          <table class="w-full text-sm">
            <thead>
              <tr style="background:#f7f5ef;">
                <th class="text-left px-3 py-2 text-xs font-bold text-ads-dim border-b border-ads-border">名称</th>
                <th class="text-right px-3 py-2 text-xs font-bold text-ads-dim border-b border-ads-border">生産性</th>
                <th class="text-right px-3 py-2 text-xs font-bold text-ads-dim border-b border-ads-border">標準比</th>
                <th class="text-center px-3 py-2 text-xs font-bold text-ads-dim border-b border-ads-border">判定</th>
              </tr>
            </thead>
            <tbody>{''.join(rows)}
            </tbody>
          </table>
        </div>'''


# ====================================================================
# コメント自動生成
# ====================================================================

def comments_overview(bureaus: list, baseline: float) -> str:
    n = len(bureaus)
    if n == 0:
        return ""
    top    = bureaus[0]
    bottom = bureaus[-1]
    achieved = [b for b in bureaus if b["standard_ratio"] >= 1.0]
    under90  = [b for b in bureaus if b["standard_ratio"] < 0.9]

    lines = []
    if achieved:
        names = "・".join(b["name"] for b in achieved)
        lines.append(f"・{names}は基準値{baseline:.0f}件/hを達成。安定した水準を維持している。")
    else:
        lines.append(f"・全{n}支社が基準値{baseline:.0f}件/hを下回っており、達成支社はゼロ。全体的な底上げが急務。")

    gap = top["avg_productivity"] - bottom["avg_productivity"]
    lines.append(f"・支社間の生産性格差は{gap:.1f}件/h（{top['name']} vs {bottom['name']}）。この差が配置効率の乖離に直結している。")

    if under90:
        names = "・".join(b["name"] for b in under90)
        lines.append(f"・{names}は標準比90%を下回り「未達成」ゾーン。改善施策と原因分析の優先度が高い。")

    return "\n".join(f"          <p>{l}</p>" for l in lines)


def comments_individual(individuals: list, baseline: float) -> str:
    n = len(individuals)
    if n == 0:
        return ""
    top      = individuals[0]
    bottom   = individuals[-1]
    achieved = [p for p in individuals if p["standard_ratio"] >= 1.0]
    under90  = [p for p in individuals if p["standard_ratio"] < 0.9]

    lines = []
    if achieved:
        pct = round(len(achieved) / n * 100)
        lines.append(f"・達成者は{len(achieved)}名/{n}名（{pct}%）。{top['name']}が{top['avg_productivity']:.1f}件/hでトップ。")
    else:
        lines.append(f"・{n}名全員が基準値{baseline:.0f}件/hを下回っている。チーム全体でのスキル底上げが課題。")

    gap = top["avg_productivity"] - bottom["avg_productivity"]
    if gap > 2:
        lines.append(f"・個人間格差は{gap:.1f}件/h（{top['name']} vs {bottom['name']}）。ナレッジ共有による平準化を検討する。")

    if under90:
        names = "・".join(p["name"] for p in under90[:3])
        if len(under90) > 3:
            names += "ほか"
        lines.append(f"・{names}は90%未満。個別サポートが必要。")

    return "\n".join(f"          <p>{l}</p>" for l in lines)


# ====================================================================
# HTML ヘッド / フッター
# ====================================================================

def html_head(title: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">
  <meta name="googlebot" content="noindex, nofollow">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&family=Inter:wght@400;500;600;700;900&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            ads: {{
              bg: '#f1efe7', surface: '#fff', hover: '#f7f5ef', border: '#e5e2d9',
              accent: '#ff4e00', 'accent-light': '#cc3e00',
              text: '#343430', muted: '#666460', dim: '#9a9690',
              positive: '#059669', negative: '#cc3e00', warning: '#ff9966',
            }}
          }},
          fontFamily: {{
            sans: ['"Noto Sans JP"', 'sans-serif'],
            mono: ['"Inter"', 'monospace']
          }}
        }}
      }}
    }}
  </script>
  <style>@media print {{ .no-print {{ display: none !important; }} body {{ border-top: none !important; }} }}</style>
</head>'''

HTML_FOOT = '''  <script src="https://unpkg.com/lucide@latest"></script>
  <script>lucide.createIcons();</script>
</body>
</html>'''


# ====================================================================
# ページ生成
# ====================================================================

def generate_overview(metrics: dict) -> str:
    bureaus    = metrics["bureaus"]
    baseline   = metrics["baseline_productivity"]
    work_hours = metrics.get("work_hours_per_day", 7.0)
    period     = metrics["period"]
    p_start    = format_date(period["start"])
    p_end      = format_date(period["end"])
    n_days     = period["days"]
    n_bureaus  = len(bureaus)
    total_staff = sum(b["staff_count"] for b in bureaus)
    all_dates   = sorted({d for b in bureaus for d in b["daily_productivity"]})

    avg_prod  = sum(b["avg_productivity"] for b in bureaus) / n_bureaus if n_bureaus else 0
    avg_ratio = round(avg_prod / baseline * 100) if baseline else 0
    trend_icon  = "trending-down" if avg_ratio < 100 else "trending-up"
    trend_color = "#ff4e00" if avg_ratio < 100 else "#059669"

    top    = bureaus[0] if bureaus else None
    bottom = bureaus[-1] if bureaus else None

    top_card = ""
    if top:
        tp = round(top["standard_ratio"] * 100)
        top_card = f'''
      <div class="rounded-xl p-4 border" style="background:#f0fdf4;border-color:#6ee7b7;">
        <p class="text-xs mb-1" style="color:#059669;">トップ支社</p>
        <p class="text-base font-black leading-tight text-ads-text">{top["name"]}</p>
        <div class="mt-2 flex items-center gap-1">
          <i data-lucide="trending-up" class="w-3.5 h-3.5" style="color:#059669;"></i>
          <span class="text-xs font-bold" style="color:#059669;">{top["avg_productivity"]:.1f}件/h ({tp}%)</span>
        </div>
      </div>'''

    bottom_card = ""
    if bottom:
        bp = round(bottom["standard_ratio"] * 100)
        bg_style = "background:#fff0eb;border-color:#ffd0bb;" if bp < 90 else "background:#f7f5ef;border-color:#e5e2d9;"
        b_color  = "#ff4e00" if bp < 90 else "#666460"
        label    = "要改善支社" if bp < 90 else "最下位支社"
        bottom_card = f'''
      <div class="rounded-xl p-4 border" style="{bg_style}">
        <p class="text-xs mb-1" style="color:{b_color};">{label}</p>
        <p class="text-base font-black leading-tight text-ads-text">{bottom["name"]}</p>
        <div class="mt-2 flex items-center gap-1">
          <i data-lucide="alert-triangle" class="w-3.5 h-3.5" style="color:{b_color};"></i>
          <span class="text-xs font-bold" style="color:{b_color};">{bottom["avg_productivity"]:.1f}件/h ({bp}%)</span>
        </div>
      </div>'''

    top_name    = bureaus[0]["name"] if bureaus else ""
    bottom_name = bureaus[-1]["name"] if bureaus else ""

    html  = html_head("生産性ダッシュボード — 支社別ビュー")
    html += f'''
<body class="bg-ads-bg text-ads-muted antialiased leading-relaxed border-t-4 border-ads-accent">
  <div class="no-print max-w-3xl mx-auto px-5 pt-2 flex justify-end">
    <button onclick="window.print()" class="flex items-center gap-1.5 text-xs text-ads-dim hover:text-ads-accent cursor-pointer">
      <i data-lucide="download" class="w-3.5 h-3.5"></i>PDF
    </button>
  </div>
  <main class="max-w-3xl mx-auto px-5 py-8">

    <div class="mb-6">
      <span class="text-xs font-bold tracking-widest uppercase" style="color:#ff4e00;">生産性レポート</span>
      <h1 class="text-2xl font-black text-ads-text mb-1 mt-1">生産性ダッシュボード</h1>
      <p class="text-sm text-ads-muted">支社ごとの生産性・標準比・人員配置を横断比較。ボトルネック支社と過剰配置を即座に把握する。</p>
    </div>

    <div class="flex gap-1 mb-6 rounded-xl p-1 border border-ads-border" style="background:#f7f5ef;">
      <div class="flex-1 bg-ads-surface rounded-lg px-4 py-2.5 text-center shadow-sm border border-ads-border">
        <div class="flex items-center justify-center gap-2">
          <i data-lucide="bar-chart-3" class="w-4 h-4 text-ads-accent"></i>
          <span class="text-sm font-bold text-ads-accent">支社別ビュー</span>
        </div>
        <p class="text-xs text-ads-dim mt-0.5">支社単位の横比較</p>
      </div>
      <a href="dashboard-individual.html" class="flex-1 rounded-lg px-4 py-2.5 text-center hover:bg-ads-surface transition-colors">
        <div class="flex items-center justify-center gap-2">
          <i data-lucide="users" class="w-4 h-4 text-ads-dim"></i>
          <span class="text-sm font-medium text-ads-muted">個人別ビュー</span>
        </div>
        <p class="text-xs text-ads-dim mt-0.5">支社フィルタ → 個人詳細</p>
      </a>
    </div>

    <div class="bg-ads-surface rounded-xl border border-ads-border p-4 mb-6">
      <div class="flex flex-wrap items-center gap-2 mb-3">
        <span class="text-xs font-bold text-ads-dim">集計期間</span>
        <div class="flex items-center gap-1.5 border border-ads-border rounded-lg px-2.5 py-1.5" style="background:#f7f5ef;">
          <i data-lucide="calendar" class="w-3.5 h-3.5 text-ads-dim"></i>
          <span class="text-sm font-medium text-ads-text">{p_start}</span>
        </div>
        <span class="text-xs text-ads-dim">—</span>
        <div class="flex items-center gap-1.5 border border-ads-border rounded-lg px-2.5 py-1.5" style="background:#f7f5ef;">
          <i data-lucide="calendar" class="w-3.5 h-3.5 text-ads-dim"></i>
          <span class="text-sm font-medium text-ads-text">{p_end}</span>
        </div>
      </div>
      <div class="flex flex-wrap gap-x-5 gap-y-0.5 pt-3 border-t border-ads-border text-xs text-ads-dim">
        <span class="flex items-center gap-1"><i data-lucide="building-2" class="w-3 h-3"></i>対象支社 <strong class="text-ads-text ml-0.5">{n_bureaus}局</strong></span>
        <span class="flex items-center gap-1"><i data-lucide="users" class="w-3 h-3"></i>総スタッフ <strong class="text-ads-text ml-0.5">{total_staff}名</strong></span>
        <span class="flex items-center gap-1"><i data-lucide="clock" class="w-3 h-3"></i>{n_days}日間</span>
        <span class="flex items-center gap-1"><i data-lucide="target" class="w-3 h-3 text-ads-accent"></i>基準値 <strong class="text-ads-accent ml-0.5">{baseline:.0f}件/h</strong></span>
      </div>
    </div>

    <div class="grid grid-cols-3 gap-3 mb-8">
      <div class="bg-ads-surface rounded-xl p-4 border border-ads-border">
        <p class="text-xs text-ads-dim mb-1">全支社平均 生産性</p>
        <p class="text-2xl font-black text-ads-text" style="font-family:'Inter',sans-serif;">{avg_prod:.1f}<span class="text-sm font-medium text-ads-muted ml-1">件/h</span></p>
        <div class="mt-2 flex items-center gap-1">
          <i data-lucide="{trend_icon}" class="w-3.5 h-3.5" style="color:{trend_color};"></i>
          <span class="text-xs font-medium" style="color:{trend_color};">基準比 {avg_ratio}%</span>
        </div>
      </div>
      {top_card}
      {bottom_card}
    </div>

    <!-- セクション1: 支社別ランキング -->
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-4">
        <div class="w-1 h-5 rounded-full bg-ads-text"></div>
        <h2 class="text-base font-bold text-ads-text">支社別ランキング</h2>
        <span class="text-xs text-ads-dim px-2 py-0.5 rounded-full border border-ads-border" style="background:#f7f5ef;">生産性 / 標準比</span>
      </div>
      <div class="bg-ads-surface rounded-xl border border-ads-border p-4">
        <p class="text-xs font-bold text-ads-dim mb-3 uppercase tracking-wide">生産性（1時間あたり処理件数）</p>
        {bar_chart_svg(bureaus, baseline)}
        <p class="text-xs font-bold text-ads-dim mb-3 uppercase tracking-wide">標準比（基準値{baseline:.0f}件/h に対する達成率）</p>
        {rank_table_html(bureaus)}
        <div class="space-y-1.5 text-xs text-ads-muted leading-relaxed">
{comments_overview(bureaus, baseline)}
        </div>
      </div>
    </div>

    <!-- セクション2: 支社別日別トレンド -->
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-4">
        <div class="w-1 h-5 rounded-full bg-ads-text"></div>
        <h2 class="text-base font-bold text-ads-text">支社別日別トレンド</h2>
      </div>
      <div class="bg-ads-surface rounded-xl border border-ads-border p-4">
        <p class="text-xs font-bold text-ads-dim mb-3 uppercase tracking-wide">日別生産性の推移（件/h）</p>
        {line_chart_svg(bureaus, all_dates)}
        <div class="flex gap-4 mt-2 flex-wrap">
          <div class="flex items-center gap-1.5 text-xs text-ads-muted">
            <div class="w-5 h-0.5 rounded" style="background:#059669;"></div> 上位（{top_name}）
          </div>
          <div class="flex items-center gap-1.5 text-xs text-ads-muted">
            <div class="w-5 h-0.5 rounded" style="background:#aaa9a6;"></div> 中位
          </div>
          <div class="flex items-center gap-1.5 text-xs text-ads-muted">
            <div class="w-5 border-t-2 border-dashed" style="border-color:#ff4e00;"></div> 下位（{bottom_name}）
          </div>
        </div>
      </div>
    </div>

    <!-- セクション3: 人員過不足アラート -->
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-4">
        <div class="w-1 h-5 rounded-full bg-ads-text"></div>
        <h2 class="text-base font-bold text-ads-text">人員過不足アラート</h2>
        <span class="text-xs text-ads-dim px-2 py-0.5 rounded-full border border-ads-border" style="background:#f7f5ef;">散布図</span>
      </div>
      <div class="bg-ads-surface rounded-xl border border-ads-border p-4">
        <p class="text-xs font-bold text-ads-dim mb-3 uppercase tracking-wide">1人あたり投入量 × 消化率（最終日）</p>
        {scatter_svg(bureaus, baseline, work_hours, period["end"])}
        <p class="mt-2 text-xs text-ads-muted">右下（高物量・低消化）ゾーンの支社が人員不足の可能性あり。適正ライン = {threshold:.0f}件/人、危険ライン = {danger:.0f}件/人。</p>
      </div>
    </div>

  </main>
  <footer class="max-w-3xl mx-auto px-5 pb-8 pt-4 border-t border-ads-border">
    <p class="text-xs text-ads-dim text-center">集計期間: {p_start} — {p_end} ／ 基準値: {baseline:.0f}件/h</p>
  </footer>
'''.format(threshold=work_hours * baseline, danger=(work_hours + 1) * baseline)
    html += HTML_FOOT
    return html


def generate_individual(metrics: dict) -> str:
    bureaus    = metrics["bureaus"]
    baseline   = metrics["baseline_productivity"]
    period     = metrics["period"]
    p_start    = format_date(period["start"])
    p_end      = format_date(period["end"])
    n_days     = period["days"]
    n_bureaus  = len(bureaus)

    sections = []
    for bi, bureau in enumerate(bureaus):
        individuals = bureau.get("individuals", [])
        if not individuals:
            continue

        all_dates = sorted({d for ind in individuals for d in ind["daily_productivity"]})
        color     = rank_color(bi, n_bureaus)
        bp        = round(bureau["standard_ratio"] * 100)

        sections.append(f'''
    <div class="mb-10 pt-6 border-t border-ads-border">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-2 h-6 rounded-full" style="background:{color};"></div>
        <div>
          <h2 class="text-base font-bold text-ads-text">{bureau["name"]}</h2>
          <p class="text-xs text-ads-dim">平均 {bureau["avg_productivity"]:.1f}件/h ／ 標準比 {bp}% ／ {bureau["staff_count"]}名</p>
        </div>
      </div>

      <div class="bg-ads-surface rounded-xl border border-ads-border p-4 mb-4">
        <p class="text-xs font-bold text-ads-dim mb-3 uppercase tracking-wide">個人別ランキング</p>
        {bar_chart_svg(individuals, baseline)}
        {rank_table_html(individuals)}
        <div class="space-y-1.5 text-xs text-ads-muted leading-relaxed">
{comments_individual(individuals, baseline)}
        </div>
      </div>

      <div class="bg-ads-surface rounded-xl border border-ads-border p-4">
        <p class="text-xs font-bold text-ads-dim mb-3 uppercase tracking-wide">個人別 日別生産性トレンド</p>
        {line_chart_svg(individuals, all_dates, height=160)}
      </div>
    </div>''')

    html  = html_head("生産性ダッシュボード — 個人別ビュー")
    html += f'''
<body class="bg-ads-bg text-ads-muted antialiased leading-relaxed border-t-4 border-ads-accent">
  <div class="no-print max-w-3xl mx-auto px-5 pt-2 flex justify-end">
    <button onclick="window.print()" class="flex items-center gap-1.5 text-xs text-ads-dim hover:text-ads-accent cursor-pointer">
      <i data-lucide="download" class="w-3.5 h-3.5"></i>PDF
    </button>
  </div>
  <main class="max-w-3xl mx-auto px-5 py-8">

    <div class="mb-6">
      <span class="text-xs font-bold tracking-widest uppercase" style="color:#ff4e00;">生産性レポート</span>
      <h1 class="text-2xl font-black text-ads-text mb-1 mt-1">生産性ダッシュボード</h1>
      <p class="text-sm text-ads-muted">支社別に個人の生産性推移を追跡する。</p>
    </div>

    <div class="flex gap-1 mb-6 rounded-xl p-1 border border-ads-border" style="background:#f7f5ef;">
      <a href="dashboard-overview.html" class="flex-1 rounded-lg px-4 py-2.5 text-center hover:bg-ads-surface transition-colors">
        <div class="flex items-center justify-center gap-2">
          <i data-lucide="bar-chart-3" class="w-4 h-4 text-ads-dim"></i>
          <span class="text-sm font-medium text-ads-muted">支社別ビュー</span>
        </div>
        <p class="text-xs text-ads-dim mt-0.5">支社単位の横比較</p>
      </a>
      <div class="flex-1 bg-ads-surface rounded-lg px-4 py-2.5 text-center shadow-sm border border-ads-border">
        <div class="flex items-center justify-center gap-2">
          <i data-lucide="users" class="w-4 h-4 text-ads-accent"></i>
          <span class="text-sm font-bold text-ads-accent">個人別ビュー</span>
        </div>
        <p class="text-xs text-ads-dim mt-0.5">支社フィルタ → 個人詳細</p>
      </div>
    </div>

    <div class="bg-ads-surface rounded-xl border border-ads-border p-4 mb-6">
      <div class="flex flex-wrap gap-x-5 gap-y-0.5 text-xs text-ads-dim">
        <span class="flex items-center gap-1"><i data-lucide="building-2" class="w-3 h-3"></i>対象支社 <strong class="text-ads-text ml-0.5">{n_bureaus}局</strong></span>
        <span class="flex items-center gap-1"><i data-lucide="clock" class="w-3 h-3"></i>{n_days}日間</span>
        <span class="flex items-center gap-1"><i data-lucide="target" class="w-3 h-3 text-ads-accent"></i>基準値 <strong class="text-ads-accent ml-0.5">{baseline:.0f}件/h</strong></span>
        <span class="flex items-center gap-1"><i data-lucide="calendar" class="w-3 h-3"></i>{p_start} — {p_end}</span>
      </div>
    </div>

    {''.join(sections)}

  </main>
  <footer class="max-w-3xl mx-auto px-5 pb-8 pt-4 border-t border-ads-border">
    <p class="text-xs text-ads-dim text-center">集計期間: {p_start} — {p_end} ／ 基準値: {baseline:.0f}件/h</p>
  </footer>
'''
    html += HTML_FOOT
    return html


INDEX_REDIRECT = '''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0; url=dashboard-overview.html">
</head><body></body></html>'''


# ====================================================================
# エントリーポイント
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="metrics.json から KPI ダッシュボード HTML を生成")
    parser.add_argument("metrics_json", help="calc-metrics.py の出力 JSON ファイル")
    parser.add_argument("--output-dir", default="output", help="出力先ディレクトリ（デフォルト: output）")
    args = parser.parse_args()

    if not os.path.exists(args.metrics_json):
        print(f"ERROR: ファイルが見つかりません: {args.metrics_json}")
        sys.exit(1)

    with open(args.metrics_json, encoding="utf-8") as f:
        metrics = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    overview_path    = os.path.join(args.output_dir, "dashboard-overview.html")
    individual_path  = os.path.join(args.output_dir, "dashboard-individual.html")
    index_path       = os.path.join(args.output_dir, "index.html")

    with open(overview_path,   "w", encoding="utf-8") as f:
        f.write(generate_overview(metrics))
    with open(individual_path, "w", encoding="utf-8") as f:
        f.write(generate_individual(metrics))
    with open(index_path,      "w", encoding="utf-8") as f:
        f.write(INDEX_REDIRECT)

    print(f"✓ 生成完了")
    print(f"  {overview_path}")
    print(f"  {individual_path}")
    print(f"  {index_path}")


if __name__ == "__main__":
    main()
