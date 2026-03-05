import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

# 日本時間(JST)の設定
JST = timezone(timedelta(hours=+9), 'JST')

def judge_stock(ticker_code, name):
    try:
        ticker = f"{ticker_code}.T"
        # 直近の動きを確実に捉えるため、期間を絞って取得
        data = yf.download(ticker, period="1mo", interval="1d", progress=False)
        if data.empty or len(data) < 25: return None

        close = data['Close']
        p_now = float(close.iloc[-1])

        # 【検証用：フィルターを大幅に緩和】
        # 株価100円未満、または出来高が極端にゼロなものだけ除外
        if p_now < 100: return None
        if data['Volume'].iloc[-1] < 1000: return None

        ma5 = close.rolling(5).mean()
        ma25 = close.rolling(25).mean()
        
        m5_now, m5_pre = float(ma5.iloc[-1]), float(ma5.iloc[-2])
        m25_now, m25_pre = float(ma25.iloc[-1]), float(ma25.iloc[-2])
        
        info = f"{ticker_code} {name}"

        # --- 判定ロジック：警告（売り）を最優先でチェック ---
        
        # ⚠️【警戒：売り】デッドクロス（5日線が25日線を下抜けた）
        if m5_pre >= m25_pre and m5_now < m25_now:
            return ("SELL", f"⚠️【警戒】{info}({p_now:.1f}円/DC発生)")
            
        # 📈【通常：買い】ゴールデンクロス
        if m5_pre <= m25_pre and m5_now > m25_now:
            return ("BUY", f"📈【買い】{info}({p_now:.1f}円/GC成立)")
            
        return None
    except:
        return None

def send_line(message):
    token = os.environ.get('LINE_ACCESS_TOKEN')
    user_id = os.environ.get('LINE_USER_ID')
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # LINEの制限に合わせ分割送信
    for i in range(0, len(message), 4500):
        payload = {"to": user_id, "messages": [{"type": "text", "text": message[i:i+4500]}]}
        requests.post(url, headers=headers, json=payload, timeout=10)
        time.sleep(1)

def main():
    target = "all_stocks.csv" if os.path.exists("all_stocks.csv") else "kabumini.csv"
    if not os.path.exists(target): return

    try:
        df = pd.read_csv(target, encoding='utf-8-sig')
        c_col = [c for c in df.columns if 'コード' in str(c) or 'Code' in str(c)][0]
        n_col = [c for c in df.columns if '銘柄' in str(c) or '名称' in str(c)][0]
        stocks = df[[c_col, n_col]].dropna().values.tolist()
        print(f"Checking {len(stocks)} stocks...")
    except:
        return

    res = {"SELL":[], "BUY":[]}
    
    for i, (code, name) in enumerate(stocks):
        c = str(code).strip()[:4]
        if len(c) == 4:
            out = judge_stock(c, str(name))
            if out:
                res[out[0]].append(out[1])
        
        if (i + 1) % 20 == 0: time.sleep(0.05)
        if (i + 1) % 500 == 0: print(f"{i+1} processed...")

    # 日本時間の現在時刻を取得
    now_jst = datetime.now(JST)
    date_str = now_jst.strftime('%m/%d %H:%M')
    
    msg = f"📊 {date_str} 判定（警告優先モード）\n"
    msg += "\n【⚠️警戒：売りサイン】\n" + ("\n".join(res["SELL"]) if res["SELL"] else "なし")
    msg += "\n\n【📈買いサイン：参考】\n" + ("\n".join(res["BUY"]) if res["BUY"] else "なし")
    
    send_line(msg)

if __name__ == "__main__":
    main()
