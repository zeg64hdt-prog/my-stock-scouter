import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

# 日本時間(JST)の設定
JST = timezone(timedelta(hours=+9), 'JST')

def judge_stock(ticker_code, name):
    try:
        ticker = f"{ticker_code}.T"
        # 過去半年分のデータを取得
        data = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if data.empty or len(data) < 75: return None

        close = data['Close']
        vol = data['Volume']
        p_now = float(close.iloc[-1])

        # --- 【ローリスク・フィルター】 ---
        
        # 1. 低位株の排除（株価500円未満はボラティリティが高いため除外）
        if p_now < 500: return None
        
        # 2. 流動性の確保（直近5日平均の売買代金が概算5,000万円未満は除外）
        avg_vol_5d = vol.tail(5).mean()
        if (p_now * avg_vol_5d) < 50_000_000: return None

        # テクニカル指標の計算
        ma5 = close.rolling(5).mean()
        ma25 = close.rolling(25).mean()
        ma75 = close.rolling(75).mean()
        vol_avg_prev = vol.shift(1).rolling(5).mean()

        m5_now, m5_pre = float(ma5.iloc[-1]), float(ma5.iloc[-2])
        m25_now, m25_pre = float(ma25.iloc[-1]), float(ma25.iloc[-2])
        m75_now, m75_pre = float(ma75.iloc[-1]), float(ma75.iloc[-2])
        v_now, v_a_pre = float(vol.iloc[-1]), float(vol_avg_prev.iloc[-1])
        
        # 3. 25日線乖離率のチェック（高値掴み防止：5%以上離れていたら除外）
        deviation = (p_now - m25_now) / m25_now
        if deviation > 0.05: return None

        info = f"{ticker_code} {name}"

        # --- 判定ロジック ---

        # ①【⚠️警戒】デッドクロス（保有銘柄の出口戦略として）
        if m5_pre >= m25_pre and m5_now < m25_now:
            return ("SELL", f"⚠️【警戒】{info}({p_now:.1f}円/DC)")

        # ②【🚀特選】GC + 25日線上向き + 出来高1.5倍（勢いのある初動）
        if m5_pre <= m25_pre and m5_now > m25_now:
            if v_now > (v_a_pre * 1.5) and m25_now > m25_pre:
                return ("BUY_SPECIAL", f"🚀【特選】{info}({p_now:.1f}円/出来高増)")
            # 通常のGCは通知過多を防ぐため、今回はあえて「なし」に設定（必要なら戻せます）
            return None

        # ③【💎転換】長期線(75日)突破（大底からの反転）
        if close.iloc[-2] <= m75_pre and p_now > m75_now and v_now > v_a_pre:
            return ("TURNOVER", f"💎【転換】{info}({p_now:.1f}円/長期線突破)")

        return None
    except:
        return None

def send_line(message):
    token = os.environ.get('LINE_ACCESS_TOKEN')
    user_id = os.environ.get('LINE_USER_ID')
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # LINEの5000文字制限対策
    for i in range(0, len(message), 4500):
        payload = {"to": user_id, "messages": [{"type": "text", "text": message[i:i+4500]}]}
        requests.post(url, headers=headers, json=payload, timeout=15)
        time.sleep(1.5)

def main():
    if not os.path.exists("all_stocks.csv"): return

    try:
        df = pd.read_csv("all_stocks.csv", encoding='utf-8-sig')
        c_col = [c for c in df.columns if 'コード' in str(c) or 'Code' in str(c)][0]
        n_col = [c for c in df.columns if '銘柄' in str(c) or '名称' in str(c)][0]
        stocks = df[[c_col, n_col]].dropna().values.tolist()
    except: return

    res = {"TURNOVER":[], "BUY_SPECIAL":[], "SELL":[]}
    
    print(f"Checking {len(stocks)} stocks with Low-Risk Filter...")
    for i, (code, name) in enumerate(stocks):
        c = str(code).strip()[:4]
        if len(c) == 4:
            out = judge_stock(c, str(name))
            if out:
                res[out[0]].append(out[1])
        
        if (i + 1) % 15 == 0: time.sleep(0.05)

    now_jst = datetime.now(JST)
    msg = f"📊 {now_jst.strftime('%m/%
