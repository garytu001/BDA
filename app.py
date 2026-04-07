import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import google.generativeai as genai
from datetime import datetime, timedelta
import urllib.request
import xml.etree.ElementTree as ET
import urllib.parse
import requests  # 新增 requests 模組用來設定偽裝

# 系統與版面基礎設定
st.set_page_config(page_title="DAT.co 量化分析終端", layout="wide", initial_sidebar_state="collapsed")

# 注入自訂 CSS 優化 UI
st.markdown("""
<style>
    div.block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
    .metric-card {
        background-color: #1E2129;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #333;
        text-align: center;
        margin-bottom: 15px;
    }
    .metric-value {font-size: 24px; font-weight: bold; color: #FFFFFF;}
    .metric-label {font-size: 14px; color: #A0AEC0;}
    h4 {color: #E2E8F0; font-size: 16px; margin-bottom: 0px; padding-bottom: 0px;}
</style>
""", unsafe_allow_html=True)

st.title("MicroStrategy (MSTR) 量化指標與資產連動分析")

# --- 1. 資料獲取 (加入突破 Yahoo 阻擋的偽裝機制) ---
@st.cache_data(ttl=3600)
def get_extended_data():
    # 建立一個 Session，並把自己偽裝成 Google Chrome 瀏覽器
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    
    # 抓取資料時帶入這個偽裝的 session
    mstr = yf.Ticker("MSTR", session=session).history(period="1y")
    btc = yf.Ticker("BTC-USD", session=session).history(period="1y")
    
    mstr.index = pd.to_datetime(mstr.index).tz_localize(None).normalize()
    btc.index = pd.to_datetime(btc.index).tz_localize(None).normalize()
    
    df = pd.concat([mstr['Close'], btc['Close'], mstr['Open'], mstr['High'], mstr['Low'], mstr['Volume'], btc['Volume']], axis=1, join='inner')
    df.columns = ['MSTR_Close', 'BTC_Close', 'MSTR_Open', 'MSTR_High', 'MSTR_Low', 'MSTR_Vol', 'BTC_Vol']
    
    BTC_PER_SHARE = 0.00383
    df['Premium'] = (df['MSTR_Close'] / (df['BTC_Close'] * BTC_PER_SHARE)) - 1
    df['MSTR_BTC_Ratio'] = df['MSTR_Close'] / df['BTC_Close']
    df['Corr'] = df['MSTR_Close'].rolling(30).corr(df['BTC_Close'])
    df['MSTR_Ret'] = df['MSTR_Close'].pct_change()
    df['BTC_Ret'] = df['BTC_Close'].pct_change()
    df['MSTR_Volat'] = df['MSTR_Ret'].rolling(20).std() * (252**0.5)
    df['BTC_Volat'] = df['BTC_Ret'].rolling(20).std() * (252**0.5)
    
    return df

raw_data = get_extended_data()

# --- 2. 新聞獲取系統 ---
@st.cache_data(ttl=1800)
def get_google_news(query="MicroStrategy 比特幣"):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        return [{'title': item.find('title').text, 'link': item.find('link').text} for item in root.findall('.//item')[:5]]
    except Exception:
        return []

# --- 3. 時間區間過濾器 ---
timeframe = st.radio("分析區間", ["1個月", "3個月", "6個月", "1年"], horizontal=True, index=1)

days_map = {"1個月": 30, "3個月": 90, "6個月": 180, "1年": 365}
cutoff_date = datetime.now() - timedelta(days=days_map[timeframe])
data = raw_data[raw_data.index >= pd.Timestamp(cutoff_date)]

drawdown = (data['MSTR_Close'] / data['MSTR_Close'].cummax()) - 1

# --- 4. 頂部核心數據卡片 ---
col1, col2, col3, col4 = st.columns(4)
current_prem = data['Premium'].iloc[-1]
prem_change = current_prem - data['Premium'].iloc[-2]

with col1:
    st.markdown(f'<div class="metric-card"><div class="metric-label">MSTR 收盤價</div><div class="metric-value">${data["MSTR_Close"].iloc[-1]:.2f}</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><div class="metric-label">BTC 價格</div><div class="metric-value">${data["BTC_Close"].iloc[-1]:.2f}</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><div class="metric-label">淨值溢價率 (Premium)</div><div class="metric-value">{current_prem:.2%}</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-card"><div class="metric-label">溢價率日變動</div><div class="metric-value">{prem_change:+.2%}</div></div>', unsafe_allow_html=True)

st.write("---")

# --- 5. 圖表繪製 ---
h = 240
def format_chart(fig, is_scatter=False):
    fig.update_layout(
        height=h, margin=dict(l=5, r=5, t=15, b=5),
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    if not is_scatter:
        fig.update_xaxes(range=[data.index.min(), data.index.max()], showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#333333")
    return fig

r1_c1, r1_c2, r1_c3 = st.columns(3)
r2_c1, r2_c2, r2_c3 = st.columns(3)
r3_c1, r3_c2, r3_c3 = st.columns(3)

with r1_c1:
    st.markdown("#### MSTR 價格走勢 (K線)")
    fig1 = go.Figure(data=[go.Candlestick(x=data.index, open=data['MSTR_Open'], high=data['MSTR_High'], low=data['MSTR_Low'], close=data['MSTR_Close'])])
    st.plotly_chart(format_chart(fig1), use_container_width=True)

with r1_c2:
    st.markdown("#### BTC 價格走勢")
    fig2 = go.Figure(data=[go.Scatter(x=data.index, y=data['BTC_Close'], line=dict(color='#F7931A', width=2))])
    st.plotly_chart(format_chart(fig2), use_container_width=True)

with r1_c3:
    st.markdown("#### 淨值溢價率 (Premium to NAV)")
    fig3 = go.Figure(data=[go.Scatter(x=data.index, y=data['Premium'], fill='tozeroy', line=dict(color='#00BFFF'))])
    st.plotly_chart(format_chart(fig3), use_container_width=True)

with r2_c1:
    st.markdown("#### MSTR 交易量分析")
    fig4 = go.Figure(data=[go.Bar(x=data.index, y=data['MSTR_Vol'], marker_color='#4A5568')])
    st.plotly_chart(format_chart(fig4), use_container_width=True)

with r2_c2:
    st.markdown("#### MSTR / BTC 價格比率")
    fig5 = go.Figure(data=[go.Scatter(x=data.index, y=data['MSTR_BTC_Ratio'], line=dict(color='#9F7AEA'))])
    st.plotly_chart(format_chart(fig5), use_container_width=True)

with r2_c3:
    st.markdown("#### 30日滾動相關係數")
    fig6 = go.Figure(data=[go.Scatter(x=data.index, y=data['Corr'], line=dict(color='#48BB78'))])
    st.plotly_chart(format_chart(fig6), use_container_width=True)

with r3_c1:
    st.markdown("#### 20日年化波動率對比")
    fig7 = go.Figure()
    fig7.add_trace(go.Scatter(x=data.index, y=data['MSTR_Volat'], name='MSTR', line=dict(color='#E53E3E')))
    fig7.add_trace(go.Scatter(x=data.index, y=data['BTC_Volat'], name='BTC', line=dict(color='#F6E05E')))
    fig7.update_layout(showlegend=True, legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
    st.plotly_chart(format_chart(fig7), use_container_width=True)

with r3_c2:
    st.markdown("#### 收益連動散點圖 (Beta 分析)")
    fig8 = go.Figure(data=[go.Scatter(x=data['BTC_Ret'], y=data['MSTR_Ret'], mode='markers', marker=dict(size=5, color='#CBD5E0', opacity=0.7))])
    fig8.update_xaxes(title_text="BTC 日報酬率")
    fig8.update_yaxes(title_text="MSTR 日報酬率")
    st.plotly_chart(format_chart(fig8, is_scatter=True), use_container_width=True)

with r3_c3:
    st.markdown("#### MSTR 最大回撤率 (%)")
    fig9 = go.Figure(data=[go.Scatter(x=data.index, y=drawdown, fill='tozeroy', line=dict(color='#FC8181'))])
    st.plotly_chart(format_chart(fig9), use_container_width=True)

st.write("---")

# --- 6. 新聞資訊與語言模型分析模組 ---
r4_c1, r4_c2 = st.columns([1, 1])

news_list = get_google_news()

with r4_c1:
    st.markdown("#### 市場動態提取")
    if news_list:
        for n in news_list:
            st.markdown(f"- [{n['title']}]({n['link']})")
    else:
        st.write("目前無最新相關新聞。")

with r4_c2:
    st.markdown("#### 語言模型趨勢評估")
    api_key = st.text_input("輸入 Gemini API Key 啟用運算(我沒錢了)", type="password")
    
    if api_key and st.button("執行模型分析"):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')
            news_text = " ".join([n['title'] for n in news_list]) if news_list else "無最新新聞"
            
            prompt = f"""
            基於以下客觀數據進行分析：
            1. MSTR 當前溢價率為 {current_prem:.2%}。
            2. 30日滾動相關係數為 {data['Corr'].iloc[-1]:.2f}。
            3. 近期市場動態：{news_text}。
            
            請提供三點結構化的專業投資評估，語氣需客觀、理性。
            """
            response = model.generate_content(prompt)
            st.markdown(response.text)
        except Exception as e:
            st.error(f"模型呼叫失敗，請確認 API 狀態。錯誤碼: {e}")
