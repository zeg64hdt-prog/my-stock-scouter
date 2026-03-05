import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

# 日本時間(JST)の設定
JST = timezone(timedelta(hours=+9), 'JST')

def judge_stock(ticker_code, name):
    try:
        ticker = f"{ticker_code}.T"
        # 過去6ヶ月分のデータを取得
        data = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if data.empty or len(data) < 30: return None

        close = data['Close']
        vol = data['Volume']

        # 各種移動平均線の計算
        ma5 = close.rolling(5).mean()
        ma25 = close.rolling(25).mean()
        ma75 = close.rolling(75).mean()
        # 出来高の5日間平均（当日を含まない前日まで）
        vol_avg_5d = vol.shift(1).rolling(5).mean()

        # 直近の数値（当日と前日）
        p_now, p_pre = float(close.iloc[-1]), float(close.iloc[-2])
        m5_now, m5_pre = float(ma5.iloc[-1]), float(ma5.iloc[-2])
        m25_now, m25_pre = float(ma25.iloc[-1]), float(ma25.iloc[-2])
        m75_now, m75_pre = float(ma75.iloc[-1]), float(ma75.iloc[-2])
        v_now, v_avg = float(vol.iloc[-1]), float(vol_avg_5d.iloc[-1])
        
        info = f"{ticker_code} {name}"

        # --- 判定ロジック ---

        # ①【⚠️警戒：デッドクロス】上昇トレンド終了の兆し
        # 条件：5日線が25日線を上から下へ突き抜けた
        if m5_pre >= m25_pre and m5_now < m25_now:
            return ("SELL", f"⚠️【警戒】{info}({p_now:.1f}円/デッドクロス)")

        # ②【🚀特選：買い】強い上昇トレンドへの合流
        # 条件：GC発生 + 出来高1.5倍増 + 25日線が右肩上がり + 株価が25日線より上
        if m5_pre <= m25_pre and m5_now > m25_now:
            is_vol_shoot = v_now > (v_avg * 1.5)
            is_ma25_up = m25_now > m25_pre
            if is_vol_shoot and is_ma25_up and p_now > m25_now:
                return ("BUY_SPECIAL", f"🚀【特選】{info}({p_now:.1f}円/出来高急増)")
            return ("BUY_NORMAL", f"📈【通常】{info}({p_now:.1f}円/GC成立)")

        # ③【💎転換：ターンオーバー】長期的な底打ち
        # 条件：株価が75日線を下から上へ突き抜けた
        if p_pre <= m75_pre and p_now > m75_now:
            return ("TURNOVER", f"💎【転換】{info}({p_now:.1f}円/長期線突破)")

        return None
    except:
        return None

def send_line(message):
    token = os.environ.get('LINE_ACCESS_TOKEN')
    user_id = os.environ.get('LINE_USER_ID')
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 4500文字ごとに分割して送信
    for i in range(0, len(message), 4500):
        payload = {"to": user_id, "messages": [{"type": "text", "text": message[i:i+4500]}]}
        requests.post(url, headers=headers, json=payload, timeout=15)
        time.sleep(1.5)

def main():
    if not os.path.exists("all_stocks.csv"):
        print("CSV file not found.")
        return

    try:
        # CSV読み込み。コード列の型を文字列に固定し、余分なスペースを排除
        df = pd.read_csv("all_stocks.csv", encoding='utf-8-sig')
        c_col = [c for c in df.columns if 'コード' in str(c) or 'Code' in str(c)][0]
        n_col = [c for c in df.columns if '銘柄' in str(c) or '名称' in str(c)][0]
        stocks = df[[c_col, n_col]].dropna().values.tolist()
    except Exception as e:
        print(f"CSV read error: {e}")
        return

    res = {"TURNOVER":[], "BUY_SPECIAL":[], "BUY_NORMAL":[], "SELL":[]}
    
    print(f"Checking {len(stocks)} stocks...")
    for i, (code, name) in enumerate(stocks):
        # 130Aなどの英字入りコードにも対応
        c = str(code).strip()
        if len(c) >= 4:
            # yfinance用に先頭4文字（または英字含むコード全体）を整形
            ticker_base = c[:4]
            out = judge_stock(ticker_base, str(name))
            if out:
                res[out[0]].append(out[1])
        
        # 負荷軽減
        if (i + 1) % 15 == 0: time.sleep(0.05)
        if (i + 1) % 500 == 0: print(f"{i+1} stocks processed...")

    now_jst = datetime.now(JST)
    msg = f"📊 {now_jst.strftime('%m/%d %H:%M')} 判定結果\n"
    
    categories = [
        ("SELL", "\n【⚠️警戒：デッドクロス】"),
        ("BUY_SPECIAL", "\n【🚀特選：買い（出来高1.5倍）】"),
        ("TURNOVER", "\n【💎転換：長期線突破】"),
        ("BUY_NORMAL", "\n【📈通常：ゴールデンクロス】")
    ]
    
    for key, title in categories:
        msg += f"{title}\n" + ("\n".join(res[key]) if res[key] else "なし") + "\n"
    
    send_line(msg)

if __name__ == "__main__":
    main()
