import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import json
import os
from pathlib import Path

# ── 頁面設定 ────────────────────────────────────────────────
st.set_page_config(
    page_title="TradeLog 交易日誌",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 自訂樣式 ─────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0d0f14; }
    [data-testid="stSidebar"] { background-color: #141720; border-right: 1px solid #2a2f45; }
    .metric-card {
        background: #1e2235; border: 1px solid #2a2f45;
        border-radius: 10px; padding: 16px 20px; text-align: center;
    }
    .metric-label { font-size: 11px; color: #475569; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { font-size: 28px; font-weight: 700; margin-top: 4px; }
    .pos { color: #10b981; } .neg { color: #ef4444; } .neu { color: #3b82f6; }
    div[data-testid="stMetric"] {
        background: #1e2235; border: 1px solid #2a2f45;
        border-radius: 10px; padding: 12px 16px;
    }
    div[data-testid="stMetric"] label { color: #94a3b8 !important; font-size: 12px !important; }
    div[data-testid="stMetric"] div { color: #e2e8f0 !important; }
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    .win-badge { color: #10b981; font-weight: 600; }
    .loss-badge { color: #ef4444; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ── 資料處理函式 ──────────────────────────────────────────────
DATA_FILE = Path("data/trades.json")

def load_trades() -> pd.DataFrame:
    """從 JSON 載入交易記錄，回傳 DataFrame"""
    if not DATA_FILE.exists():
        return pd.DataFrame(columns=[
            "id", "date", "symbol", "direction", "result",
            "pnl", "fee", "net_pnl", "strategy", "session",
            "confidence", "notes"
        ])
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df["net_pnl"] = df["pnl"] - df["fee"]
    return df.sort_values("date", ascending=False).reset_index(drop=True)

def save_trade(trade: dict):
    """儲存單筆交易到 JSON"""
    DATA_FILE.parent.mkdir(exist_ok=True)
    trades = []
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            trades = json.load(f)
    # 若是編輯模式，替換原有記錄
    if "edit_id" in st.session_state and st.session_state.edit_id:
        trades = [t for t in trades if t["id"] != st.session_state.edit_id]
        st.session_state.edit_id = None
    trades.append(trade)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2, default=str)

def delete_trade(trade_id: str):
    """刪除指定 ID 的交易"""
    if not DATA_FILE.exists():
        return
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        trades = json.load(f)
    trades = [t for t in trades if t["id"] != trade_id]
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2, default=str)

def calc_stats(df: pd.DataFrame) -> dict:
    """計算所有統計指標"""
    if df.empty:
        return {k: 0 for k in ["total","wins","losses","wr","total_pnl",
                                "total_fee","net_pnl","avg_win","avg_loss",
                                "profit_factor","rr","max_streak","max_dd"]}
    wins = df[df["result"] == "WIN"]
    losses = df[df["result"] == "LOSS"]
    total_pnl = df["pnl"].sum()
    total_fee = df["fee"].sum()
    net = df["net_pnl"].sum()
    avg_win = wins["pnl"].mean() if len(wins) else 0
    avg_loss = abs(losses["pnl"].mean()) if len(losses) else 0
    pf = (wins["pnl"].sum() / abs(losses["pnl"].sum())) if len(losses) and losses["pnl"].sum() != 0 else 0
    rr = (avg_win / avg_loss) if avg_loss != 0 else 0
    # 最長連勝
    streak = max_streak = 0
    for _, row in df.sort_values("date").iterrows():
        if row["result"] == "WIN":
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    # 最大回撤
    cum = df.sort_values("date")["net_pnl"].cumsum()
    peak = cum.cummax()
    drawdown = (cum - peak)
    max_dd = drawdown.min()
    return {
        "total": len(df), "wins": len(wins), "losses": len(losses),
        "wr": (len(wins)/len(df)*100) if len(df) else 0,
        "total_pnl": total_pnl, "total_fee": total_fee, "net_pnl": net,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "profit_factor": pf, "rr": rr,
        "max_streak": max_streak, "max_dd": max_dd,
    }

# ── 圖表函式 ──────────────────────────────────────────────────
CHART_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94a3b8", size=11),
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis=dict(gridcolor="#1c2030", linecolor="#2a2f45"),
    yaxis=dict(gridcolor="#1c2030", linecolor="#2a2f45"),
)

def equity_curve_chart(df: pd.DataFrame):
    sorted_df = df.sort_values("date")
    sorted_df = sorted_df.copy()
    sorted_df["cumulative"] = sorted_df["net_pnl"].cumsum()
    color = "#10b981" if sorted_df["cumulative"].iloc[-1] >= 0 else "#ef4444"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sorted_df["date"], y=sorted_df["cumulative"],
        mode="lines", line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=color.replace(")", ",0.1)").replace("rgb", "rgba") if "rgb" in color else color+"22",
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>累積損益: $%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(**CHART_THEME, height=220)
    return fig

def monthly_pnl_chart(df: pd.DataFrame):
    df = df.copy()
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby("month")["net_pnl"].sum().reset_index()
    monthly["color"] = monthly["net_pnl"].apply(lambda x: "#10b981" if x >= 0 else "#ef4444")
    fig = go.Figure(go.Bar(
        x=monthly["month"], y=monthly["net_pnl"],
        marker_color=monthly["color"],
        hovertemplate="<b>%{x}</b><br>損益: $%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(**CHART_THEME, height=220)
    return fig

def winrate_gauge(wr: float):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=wr,
        number={"suffix": "%", "font": {"color": "#e2e8f0", "size": 32}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#475569"},
            "bar": {"color": "#3b82f6"},
            "bgcolor": "#1c2030",
            "steps": [
                {"range": [0, 40], "color": "#ef444420"},
                {"range": [40, 60], "color": "#f59e0b20"},
                {"range": [60, 100], "color": "#10b98120"},
            ],
            "threshold": {"line": {"color": "#10b981", "width": 3}, "value": 60},
        },
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8"), height=180, margin=dict(l=20,r=20,t=20,b=10))
    return fig

def strategy_chart(df: pd.DataFrame):
    strat = df.groupby("strategy").agg(
        次數=("pnl", "count"),
        總損益=("net_pnl", "sum"),
        勝率=("result", lambda x: (x == "WIN").sum() / len(x) * 100)
    ).reset_index().sort_values("總損益", ascending=True)
    fig = go.Figure(go.Bar(
        x=strat["總損益"], y=strat["strategy"],
        orientation="h",
        marker_color=strat["總損益"].apply(lambda x: "#10b981" if x >= 0 else "#ef4444"),
        hovertemplate="<b>%{y}</b><br>損益: $%{x:.2f}<extra></extra>",
    ))
    fig.update_layout(**CHART_THEME, height=max(180, len(strat)*40))
    return fig

def scatter_chart(df: pd.DataFrame):
    fig = px.scatter(
        df, x="date", y="net_pnl",
        color=df["result"].map({"WIN": "#10b981", "LOSS": "#ef4444"}),
        size=df["confidence"].clip(1, 5),
        hover_data={"symbol": True, "strategy": True, "net_pnl": ":.2f"},
        color_discrete_map="identity",
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#475569", line_width=1)
    fig.update_layout(**CHART_THEME, height=250, showlegend=False)
    return fig

# ── Session State 初始化 ──────────────────────────────────────
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None
if "page" not in st.session_state:
    st.session_state.page = "總覽"
if "delete_confirm" not in st.session_state:
    st.session_state.delete_confirm = None

# ── 側邊欄導覽 ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 TradeLog")
    st.markdown("---")
    pages = ["總覽", "新增交易", "交易記錄", "統計分析", "匯出資料"]
    icons = ["🏠", "➕", "📋", "📊", "💾"]
    for icon, page in zip(icons, pages):
        if st.button(f"{icon} {page}", use_container_width=True,
                     type="primary" if st.session_state.page == page else "secondary"):
            st.session_state.page = page
            st.session_state.edit_id = None
            st.rerun()
    st.markdown("---")
    df_all = load_trades()
    st.markdown(f"<small style='color:#475569'>共 {len(df_all)} 筆記錄</small>", unsafe_allow_html=True)
    if not df_all.empty:
        net = df_all["net_pnl"].sum()
        color = "#10b981" if net >= 0 else "#ef4444"
        st.markdown(f"<small style='color:{color}; font-weight:600'>總損益: {'+'if net>=0 else ''}${net:,.2f}</small>",
                    unsafe_allow_html=True)

# ── 載入資料 ──────────────────────────────────────────────────
df = load_trades()

# ════════════════════════════════════════════════════════════════
# 頁面 1：總覽
# ════════════════════════════════════════════════════════════════
if st.session_state.page == "總覽":
    st.title("🏠 交易總覽")

    if df.empty:
        st.info("📭 尚無交易記錄。點選側邊欄「新增交易」開始記錄！")
    else:
        s = calc_stats(df)
        # 核心指標列
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            color = "normal" if s["net_pnl"] >= 0 else "inverse"
            st.metric("💰 淨損益", f"${s['net_pnl']:+,.2f}", delta=f"手續費 ${s['total_fee']:.2f}")
        with c2:
            st.metric("🎯 勝率", f"{s['wr']:.1f}%", delta=f"{s['wins']}勝 / {s['losses']}敗")
        with c3:
            st.metric("⚖️ 盈虧比 R:R", f"{s['rr']:.2f}", delta="目標 > 1.5")
        with c4:
            st.metric("📈 獲利因子", f"{s['profit_factor']:.2f}", delta="目標 > 1.5")

        st.markdown("---")
        col_left, col_right = st.columns([3, 1])
        with col_left:
            st.markdown("**資產曲線**")
            st.plotly_chart(equity_curve_chart(df), use_container_width=True, config={"displayModeBar": False})
        with col_right:
            st.markdown("**勝率儀表**")
            st.plotly_chart(winrate_gauge(s["wr"]), use_container_width=True, config={"displayModeBar": False})

        st.markdown("**最近 10 筆交易**")
        recent = df.head(10)[["date", "symbol", "direction", "result", "net_pnl", "strategy", "confidence"]].copy()
        recent["date"] = recent["date"].dt.strftime("%Y-%m-%d")
        recent["net_pnl"] = recent["net_pnl"].apply(lambda x: f"{'+'if x>=0 else ''}${x:,.2f}")
        recent.columns = ["日期", "商品", "方向", "結果", "損益", "策略", "信心"]
        st.dataframe(recent, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# 頁面 2：新增交易
# ════════════════════════════════════════════════════════════════
elif st.session_state.page == "新增交易":
    # 編輯模式：預填欄位
    edit_data = {}
    if st.session_state.edit_id and not df.empty:
        row = df[df["id"] == st.session_state.edit_id]
        if not row.empty:
            edit_data = row.iloc[0].to_dict()
            st.title("✏️ 編輯交易記錄")
        else:
            st.title("➕ 新增交易記錄")
    else:
        st.title("➕ 新增交易記錄")

    with st.form("trade_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            trade_date = st.date_input("📅 日期",
                value=pd.to_datetime(edit_data.get("date", date.today())).date() if edit_data else date.today())
            symbol = st.text_input("💱 商品代號 (例: BTC/USDT, TSLA)",
                value=edit_data.get("symbol", "")).upper()
            direction = st.selectbox("📊 交易方向",
                ["LONG (做多)", "SHORT (做空)"],
                index=0 if edit_data.get("direction", "LONG") == "LONG" else 1)
            result = st.selectbox("🎯 交易結果",
                ["WIN (獲利)", "LOSS (虧損)"],
                index=0 if edit_data.get("result", "WIN") == "WIN" else 1)
        with col2:
            pnl_raw = st.number_input("💵 損益金額 ($)",
                min_value=0.0, value=float(abs(edit_data.get("pnl", 0))), step=10.0, format="%.2f")
            fee = st.number_input("💸 手續費 ($)",
                min_value=0.0, value=float(edit_data.get("fee", 0)), step=1.0, format="%.2f")
            strategy = st.text_input("🧠 交易策略 (例: 均線突破, 型態)",
                value=edit_data.get("strategy", ""))
            session = st.selectbox("🕐 交易時段",
                ["亞洲盤", "歐洲盤", "美洲盤", "其他"],
                index=["亞洲盤", "歐洲盤", "美洲盤", "其他"].index(edit_data.get("session", "亞洲盤")))

        confidence = st.slider("⭐ 信心分數", 1, 5,
            value=int(edit_data.get("confidence", 3)),
            help="交易當下的信心程度，1=最低 5=最高")
        notes = st.text_area("📝 交易筆記（進出場理由、教訓、複盤）",
            value=edit_data.get("notes", ""), height=100,
            placeholder="例：根據 15 分鐘 K 線突破前高進場，止損設在前低下方...")

        st.markdown("---")
        submitted = st.form_submit_button("💾 儲存記錄", use_container_width=True, type="primary")

        if submitted:
            if not symbol:
                st.error("⚠️ 請填寫商品代號！")
            else:
                is_win = "WIN" in result
                pnl = pnl_raw if is_win else -pnl_raw
                trade = {
                    "id": st.session_state.edit_id or datetime.now().strftime("%Y%m%d%H%M%S%f"),
                    "date": str(trade_date),
                    "symbol": symbol,
                    "direction": "LONG" if "LONG" in direction else "SHORT",
                    "result": "WIN" if is_win else "LOSS",
                    "pnl": pnl,
                    "fee": fee,
                    "strategy": strategy,
                    "session": session,
                    "confidence": confidence,
                    "notes": notes,
                }
                save_trade(trade)
                st.success(f"✅ 已{'更新' if st.session_state.edit_id else '儲存'}！ {symbol} | {'🟢' if is_win else '🔴'} {'+'if pnl>=0 else ''}${pnl:.2f}")
                st.session_state.edit_id = None
                st.balloons()

# ════════════════════════════════════════════════════════════════
# 頁面 3：交易記錄
# ════════════════════════════════════════════════════════════════
elif st.session_state.page == "交易記錄":
    st.title("📋 交易記錄")

    if df.empty:
        st.info("📭 尚無交易記錄。")
    else:
        # 篩選列
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            syms = ["全部"] + sorted(df["symbol"].unique().tolist())
            filter_sym = st.selectbox("商品", syms)
        with fc2:
            filter_result = st.selectbox("結果", ["全部", "WIN (獲利)", "LOSS (虧損)"])
        with fc3:
            strats = ["全部"] + sorted(df["strategy"].dropna().unique().tolist())
            filter_strat = st.selectbox("策略", strats)
        with fc4:
            filter_dir = st.selectbox("方向", ["全部", "LONG", "SHORT"])

        fdf = df.copy()
        if filter_sym != "全部":
            fdf = fdf[fdf["symbol"] == filter_sym]
        if "WIN" in filter_result:
            fdf = fdf[fdf["result"] == "WIN"]
        elif "LOSS" in filter_result:
            fdf = fdf[fdf["result"] == "LOSS"]
        if filter_strat != "全部":
            fdf = fdf[fdf["strategy"] == filter_strat]
        if filter_dir != "全部":
            fdf = fdf[fdf["direction"] == filter_dir]

        st.markdown(f"顯示 **{len(fdf)}** 筆 / 共 {len(df)} 筆")
        st.markdown("---")

        for _, row in fdf.iterrows():
            pnl = row["net_pnl"]
            is_win = row["result"] == "WIN"
            pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
            stars = "⭐" * int(row["confidence"])

            with st.expander(
                f"{'🟢' if is_win else '🔴'} {str(row['date'])[:10]} | {row['symbol']} | {row['direction']} | {'+'if pnl>=0 else ''}${pnl:,.2f}",
                expanded=False
            ):
                dc1, dc2, dc3 = st.columns(3)
                with dc1:
                    st.markdown(f"**策略：** {row['strategy'] or '—'}")
                    st.markdown(f"**時段：** {row['session']}")
                with dc2:
                    st.markdown(f"**信心：** {stars}")
                    st.markdown(f"**手續費：** ${row['fee']:.2f}")
                with dc3:
                    st.markdown(f"**毛損益：** ${row['pnl']:+,.2f}")
                    st.markdown(f"<span style='color:{pnl_color};font-weight:600'>**淨損益：** ${pnl:+,.2f}</span>", unsafe_allow_html=True)

                if row["notes"]:
                    st.markdown(f"**筆記：** {row['notes']}")

                b1, b2, _ = st.columns([1, 1, 5])
                with b1:
                    if st.button("✏️ 編輯", key=f"edit_{row['id']}"):
                        st.session_state.edit_id = row["id"]
                        st.session_state.page = "新增交易"
                        st.rerun()
                with b2:
                    if st.button("🗑️ 刪除", key=f"del_{row['id']}"):
                        delete_trade(row["id"])
                        st.success("已刪除")
                        st.rerun()

# ════════════════════════════════════════════════════════════════
# 頁面 4：統計分析
# ════════════════════════════════════════════════════════════════
elif st.session_state.page == "統計分析":
    st.title("📊 統計分析")

    if df.empty:
        st.info("📭 尚無足夠資料進行分析。")
    else:
        s = calc_stats(df)

        # 指標總覽
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("總交易數", s["total"])
        m2.metric("勝率", f"{s['wr']:.1f}%")
        m3.metric("平均獲利", f"${s['avg_win']:,.2f}")
        m4.metric("平均虧損", f"${s['avg_loss']:,.2f}")
        m5.metric("最長連勝", f"{s['max_streak']} 筆")
        m6.metric("最大回撤", f"${s['max_dd']:,.2f}")

        st.markdown("---")

        # 每月損益 + 散點圖
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**每月損益**")
            st.plotly_chart(monthly_pnl_chart(df), use_container_width=True, config={"displayModeBar": False})
        with col2:
            st.markdown("**交易散點圖（大小=信心分數）**")
            st.plotly_chart(scatter_chart(df), use_container_width=True, config={"displayModeBar": False})

        # 策略分析
        if df["strategy"].notna().any() and df["strategy"].ne("").any():
            st.markdown("**策略損益排名**")
            st.plotly_chart(strategy_chart(df[df["strategy"] != ""]), use_container_width=True, config={"displayModeBar": False})

        # 時段分析
        st.markdown("**時段表現**")
        session_stats = df.groupby("session").agg(
            次數=("pnl", "count"),
            勝率=("result", lambda x: f"{(x=='WIN').mean()*100:.0f}%"),
            總損益=("net_pnl", lambda x: f"{'+'if x.sum()>=0 else ''}${x.sum():,.2f}"),
            平均損益=("net_pnl", lambda x: f"{'+'if x.mean()>=0 else ''}${x.mean():,.2f}"),
        ).reset_index()
        session_stats.columns = ["時段", "次數", "勝率", "總損益", "平均損益"]
        st.dataframe(session_stats, use_container_width=True, hide_index=True)

        # 商品分析
        st.markdown("**商品表現**")
        sym_stats = df.groupby("symbol").agg(
            次數=("pnl", "count"),
            勝率=("result", lambda x: f"{(x=='WIN').mean()*100:.0f}%"),
            總損益=("net_pnl", lambda x: f"{'+'if x.sum()>=0 else ''}${x.sum():,.2f}"),
        ).reset_index().sort_values("次數", ascending=False)
        sym_stats.columns = ["商品", "次數", "勝率", "總損益"]
        st.dataframe(sym_stats, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# 頁面 5：匯出資料
# ════════════════════════════════════════════════════════════════
elif st.session_state.page == "匯出資料":
    st.title("💾 匯出資料")

    if df.empty:
        st.info("📭 尚無資料可匯出。")
    else:
        st.markdown(f"共 **{len(df)}** 筆交易記錄可供匯出。")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 📄 匯出為 CSV（Excel 可開啟）")
            export_df = df.copy()
            export_df["date"] = export_df["date"].dt.strftime("%Y-%m-%d")
            csv = export_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("⬇️ 下載 CSV", csv, "trades.csv", "text/csv", use_container_width=True)
        with col2:
            st.markdown("#### 🗂️ 匯出為 JSON（完整備份）")
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                json_data = f.read()
            st.download_button("⬇️ 下載 JSON", json_data, "trades_backup.json", "application/json", use_container_width=True)

        st.markdown("---")
        st.markdown("#### 📊 資料預覽")
        preview = df[["date", "symbol", "direction", "result", "pnl", "fee", "net_pnl", "strategy", "session", "confidence"]].copy()
        preview["date"] = preview["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(preview, use_container_width=True, hide_index=True)
