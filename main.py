import os, requests, pandas as pd, yfinance as yf, time
from datetime import datetime

def judge_stock(ticker_code, name):
    try:
        ticker = f"{ticker_code}.T"
        data = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if data.empty or len(data) < 75: return None

        close = data['Close']
        p_now = float(close.iloc[-1])

        # 【絞り込み】株価500円未満、または5日平均出来高が5万株未満は無視
        if p_now < 500: return None
        if data['Volume'].tail(5).mean() < 50000: return None

        ma5, ma25, ma75 = close.rolling(5).mean(), close.rolling(25).mean(), close.rolling(75).mean()
        v_avg = data['Volume'].shift(1).rolling(5).mean()
        
        m5, m25, m75 = ma5.iloc[-1], ma25.iloc[-1], ma75.iloc[-1]
        m5_p, m25_p, m75_p = ma5.iloc[-2], ma25.iloc[-2], ma75.iloc[-2]
        v_now, v_a = data['Volume'].iloc[-1], v_avg.iloc[-1]
        info = f"{ticker_code} {name}"

        # 判定
        if close.iloc[-2] <= m75_p and p_now > m75:
            return ("TURNOVER", f"💎【転換】{info}({p_now:.1f}円)")
        if m5_p <= m25_p and m5 > m25:
            if v_now > (v_a * 1.5): return ("BUY_SPECIAL", f"🚀【特選】{info}({p_now:.1f}円)")
            return ("BUY_NORMAL", f"📈{info}({p_now:.1f}円)")
        if m5_p >= m25_p and m5 < m25:
            return ("SELL", f"⚠️{info}({p_now:.1f}円)")
        return None
    except: return None

def send_line(message):
    token, uid = os.environ.get('LINE_ACCESS_TOKEN'), os.environ.get('LINE_USER_ID')
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for i in range(0, len(message), 4500):
        payload = {"to": uid, "messages": [{"type": "text", "text": message[i:i+4500]}]}
        requests.post(url, headers=headers, json=payload, timeout=10)
        time.sleep(1)

def main():
    if not os.path.exists("all_stocks.csv"): return
    try:
        df = pd.read_csv("all_stocks.csv", encoding='utf-8-sig')
        c_col = [c for c in df.columns if 'コード' in str(c) or 'Code' in str(c)][0]
        n_col = [c for c in df.columns if '銘柄' in str(c) or '名称' in str(c)][0]
        stocks = df[[c_col, n_col]].dropna().values.tolist()
    except: return

    res = {"TURNOVER":[], "BUY_SPECIAL":[], "BUY_NORMAL":[], "SELL":[]}
    for i, (code, name) in enumerate(stocks):
        c = str(code).strip()[:4]
        if len(c) == 4:
            out = judge_stock(c, str(name))
            if out: res[out[0]].append(out[1])
        if (i+1)%15 == 0: time.sleep(0.05)
    
    msg = f"📊 {datetime.now().strftime('%m/%d')} 判定結果\n"
    for k, t in [("TURNOVER","💎転換"), ("BUY_SPECIAL","🚀特選"), ("BUY_NORMAL","📈通常"), ("SELL","⚠️警戒")]:
        msg += f"\n【{t}】\n" + ("\n".join(res[k]) if res[k] else "なし")
    send_line(msg)

if __name__ == "__main__":
    main()
