import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

# 日本時間(JST)の設定
JST = timezone(timedelta(hours=+9), 'JST')

def judge_stock(ticker_code, name):
    try:
        ticker = f"{ticker_code}.T"
        # データ取得期間を6ヶ月に設定
        data = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if data.empty or len(data) < 75: return None

        close = data['Close']
        vol = data['Volume']
        p_now = float(close.iloc[-1])

        # --- 【ローリスク・フィルター】 ---
        # 1. 株価500円未満を排除
        if p_now < 500: return None
        
        # 2. 流動性確保（5日平均売買代金が概算5,000万円未満は除外）
        avg_vol_5d = vol.tail(5).mean()
        if (p_now * avg_vol_5d) < 50000000: return None

        # テクニカル指標計算
        ma5 = close.rolling(5).mean()
        ma25 = close.rolling(25).mean()
        ma75 = close.rolling(75).mean()
        vol_avg_prev = vol.shift(1).rolling(5).mean()

        m5_now, m5_pre = float(ma5.iloc[-1]), float(ma5.iloc[-2])
        m25_now, m25_pre = float(ma25.iloc[-1]), float(ma25.iloc[-2])
        m75_now, m75_pre = float(ma75.iloc[-1]), float(ma75.iloc[-2])
        v_now, v_a_pre = float(vol.iloc[-1]), float(vol_avg_prev.iloc[-1])
        
        # 3. 25日線乖離率（高値掴み防止：5%超は除外）
        deviation = (p_now - m25_now) / m25_now
        if deviation > 0.05: return None

        info = f"{ticker_code} {name}"

        # --- 判定ロジック ---
        # ①【⚠️警戒】デッドクロス（下落の初動）
        if m5_pre >= m25_pre and m5_now < m25_now:
            return ("SELL", f"⚠️【警戒】{info}({p_now:.1f}円/DC)")

        # ②【🚀特選】GC + 25日線上向き + 出来高1.5倍（勢いのある初動）
        if m5_pre <= m25_pre and m5_now > m25_now:
            if v_now > (v_a_pre * 1.5) and m25_now > m25_pre:
                return ("BUY_SPECIAL", f"🚀【特選】{info}({p_now:.1f}円/出来高増)")
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
    
    # 4500文字ごとに分割
    for i in range(0, len(message), 4500):
        payload = {"to": user_id, "messages": [{"type": "text", "text": message[i:i+4500]}]}
        try:
            requests.post(url, headers=headers, json=payload, timeout=15)
            time.sleep(1.5)
        except:
            pass

def main():
    if not os.path.exists("all_stocks.csv"):
        print("CSV not found")
        return

    try:
        df = pd.read_csv("all_stocks.csv", encoding='utf-8-sig')
        c_col = [c for c in df.columns if 'コード' in str(c) or 'Code' in str(c)][0]
        n_col = [c for c in df.columns if '銘柄' in str(c) or '名称' in str(c)][0]
        stocks = df[[c_col, n_col]].dropna().values.tolist()
    except Exception as e:
        print(f"CSV error: {e}")
        return

    res = {"TURNOVER":[], "BUY_SPECIAL":[], "SELL":[]}
    
    print(f"Checking {len(stocks)} stocks...")
    for i, (code, name) in enumerate(stocks):
        c = str(code).strip()[:4]
        if len(c) == 4:
            out = judge_stock(c, str(name))
            if out:
                res[out[0]].append(out[1])
        if (i + 1) % 15 == 0: time.sleep(0.05)

    now_jst = datetime.now(JST)
    date_str = now_jst.strftime('%m/%d %H:%M')
    
    msg = f"📊 {date_str} 厳選判定結果\n"
    msg += "条件:株価500↑/代金5千万↑/乖離5%↓\n\n"
    
    msg += "【⚠️警戒：売サイン】\n" + ("\n".join(res["SELL"]) if res["SELL"] else "なし") + "\n\n"
    msg += "【🚀特選：買サイン】\n" + ("\n".join(res["BUY_SPECIAL"]) if res["BUY_SPECIAL"] else "なし") + "\n\n"
    msg += "【💎転換：長期反転】\n" + ("\n".join(res["TURNOVER"]) if res["TURNOVER"] else "なし")
    
    send_line(msg)

if __name__ == "__main__":
    main()
