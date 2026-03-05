import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime, timedelta, timezone

# 日本時間(JST)の設定
JST = timezone(timedelta(hours=+9), 'JST')

def judge_stock(ticker_code, name):
    try:
        ticker = f"{ticker_code}.T"
        # 余裕を持って過去1年分のデータを取得
        data = yf.download(ticker, period="1y", interval="1d", progress=False)
        if data.empty or len(data) < 75: return None

        close = data['Close']
        vol = data['Volume']
        p_now = float(close.iloc[-1])

        # --- 【ローリスク・フィルター】 ---
        # ① 株価300円未満を排除（安定性重視）
        if p_now < 300: return None
        
        # ② 流動性（売買代金）が極端に低いものは除外（1日2,000万円以上）
        avg_vol_5d = vol.tail(5).mean()
        if (p_now * avg_vol_5d) < 20000000: return None

        # 指標計算
        ma5 = close.rolling(5).mean()
        ma25 = close.rolling(25).mean()
        ma75 = close.rolling(75).mean()
        vol_avg_5d = vol.shift(1).rolling(5).mean()

        m5_now, m5_pre = float(ma5.iloc[-1]), float(ma5.iloc[-2])
        m25_now, m25_pre = float(ma25.iloc[-1]), float(ma25.iloc[-2])
        m75_now, m75_pre = float(ma75.iloc[-1]), float(ma75.iloc[-2])
        v_now, v_avg = float(vol.iloc[-1]), float(vol_avg_5d.iloc[-1])
        
        # ③ 乖離率チェック（25日線から離れすぎているものは高リスクとして除外）
        dev25 = (p_now - m25_now) / m25_now
        if dev25 > 0.08: return None # 8%以上離れていたら除外

        info = f"{ticker_code} {name}"

        # --- 判定ロジック ---
        # ⚠️【警戒：デッドクロス】
        if m5_pre >= m25_pre and m5_now < m25_now:
            return ("SELL", f"⚠️【警戒】{info}({p_now:.0f}円/DC)")

        # 🚀【特選：買い】25日線が上向き、かつ出来高が普段の1.5倍
        if m5_pre <= m25_pre and m5_now > m25_now:
            if v_now > (v_avg * 1.5) and m25_now > m25_pre:
                return ("BUY", f"🚀【特選】{info}({p_now:.0f}円/出来高急増)")

        # 💎【転換：長期反転】75日線を突破
        if close.iloc[-2] <= m75_pre and p_now > m75_now:
            return ("TURN", f"💎【転換】{info}({p_now:.0f}円/底打ち気配)")

        return None
    except:
        return None

def send_line(message):
    token = os.environ.get('LINE_ACCESS_TOKEN')
    user_id = os.environ.get('LINE_USER_ID')
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
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

    res = {"SELL":[], "BUY":[], "TURN":[]}
    for i, (code, name) in enumerate(stocks):
        c = str(code).strip()[:4]
        if c.isdigit():
            out = judge_stock(c, str(name))
            if out: res[out[0]].append(out[1])
        if (i+1) % 15 == 0: time.sleep(0.02) # スピード調整

    now_jst = datetime.now(JST)
    msg = f"📊 {now_jst.strftime('%m/%d %H:%M')} 厳選ローリスク判定\n"
    msg += "条件:株価300↑/代金2千万↑/乖離8%↓\n\n"
    msg += "【⚠️警戒：売サイン】\n" + ("\n".join(res["SELL"]) if res["SELL"] else "なし") + "\n\n"
    msg += "【🚀特選：買サイン】\n" + ("\n".join(res["BUY"]) if res["BUY"] else "なし") + "\n\n"
    msg += "【💎転換：長期反転】\n" + ("\n".join(res["TURN"]) if res["TURN"] else "なし")
    send_line(msg)

if __name__ == "__main__":
    main()
