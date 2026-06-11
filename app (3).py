"""
Painel Macro Brasil — Streamlit
Fontes: Yahoo Finance · BCB SGS · BLS/FRED · RSS de notícias
"""

import math, time, requests, feedparser
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
import anthropic
from datetime import datetime, timedelta
from io import StringIO

# ── Configuração da página ────────────────────────────────────────
st.set_page_config(
    page_title="Painel Macro Brasil",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS: tema azul escuro + cores vibrantes ───────────────────────
st.markdown("""
<style>
  /* Fundo geral */
  .stApp { background-color: #0a1628; color: #e2e8f5; }
  section[data-testid="stSidebar"] { background-color: #0f2044; }

  /* Header customizado */
  .painel-header {
    display:flex; align-items:center; justify-content:space-between;
    background:linear-gradient(135deg,#060e1f 0%,#0a1628 50%,#0f2044 100%);
    border-bottom:1px solid #1e3a6e;
    padding:14px 0 12px 0; margin-bottom:20px;
  }
  .painel-title { font-size:22px; font-weight:800; color:#e2e8f5; letter-spacing:-.01em; }
  .painel-ts    { font-size:12px; color:#64748b; }
  .pulse { display:inline-block; width:9px; height:9px; border-radius:50%;
           background:#4ade80; margin-right:8px;
           box-shadow:0 0 8px rgba(74,222,128,.7); animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  /* Metric cards */
  .mcard {
    background:#0f2044; border:1px solid #1e3a6e; border-top:3px solid #38bdf8;
    border-radius:10px; padding:14px 16px; margin-bottom:6px;
  }
  .mcard-label { font-size:10px; color:#4a5568; font-weight:700;
                 text-transform:uppercase; letter-spacing:.06em; margin-bottom:6px; }
  .mcard-val   { font-size:22px; font-weight:800; color:#e2e8f5; letter-spacing:-.03em; }
  .mcard-up    { color:#4ade80; font-size:12px; font-weight:600; }
  .mcard-dn    { color:#f87171; font-size:12px; font-weight:600; }
  .mcard-neu   { color:#64748b; font-size:12px; }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    background:#0f2044; border-bottom:1px solid #1e3a6e; gap:4px;
  }
  .stTabs [data-baseweb="tab"] {
    background:transparent; color:#64748b; border-radius:6px 6px 0 0;
    font-weight:500; padding:10px 18px;
  }
  .stTabs [aria-selected="true"] {
    background:#0a1628 !important; color:#38bdf8 !important;
    border-bottom:2px solid #38bdf8 !important; font-weight:700;
  }
  .stTabs [data-baseweb="tab"]:hover { color:#94a3b8; }

  /* Tabelas */
  .dataframe { background:#0f2044 !important; color:#e2e8f5 !important; }
  thead tr th { background:#162554 !important; color:#38bdf8 !important;
                font-size:11px !important; text-transform:uppercase; }
  tbody tr:hover td { background:rgba(56,189,248,.05) !important; }

  /* Notícias */
  .news-card {
    background:#0f2044; border:1px solid #1e3a6e; border-left:3px solid #38bdf8;
    border-radius:8px; padding:12px 14px; margin-bottom:10px;
  }
  .news-source { font-size:10px; font-weight:700; text-transform:uppercase;
                 color:#38bdf8; background:rgba(56,189,248,.1);
                 padding:2px 8px; border-radius:20px; display:inline-block; margin-bottom:6px; }
  .news-title  { font-size:13px; font-weight:600; color:#e2e8f5; line-height:1.4; }
  .news-desc   { font-size:11px; color:#64748b; margin-top:4px; line-height:1.4; }
  .news-date   { font-size:10px; color:#4a5568; margin-top:4px; }

  /* Esconder elementos do Streamlit */
  #MainMenu, footer, header { visibility:hidden; }
  .block-container { padding-top:1rem; padding-bottom:1rem; }

  /* Multiselect e text_input no tema escuro */
  .stMultiSelect [data-baseweb="tag"] { background:#162554 !important; }
  .stTextInput input { background:#0f2044 !important; color:#e2e8f5 !important;
                       border-color:#1e3a6e !important; }
  .stMultiSelect > div { background:#0f2044 !important; border-color:#1e3a6e !important; }

  /* Spinner */
  .stSpinner > div { border-top-color:#38bdf8 !important; }

  /* Botões */
  .stButton > button {
    background:#162554 !important; color:#38bdf8 !important;
    border:1px solid #1e3a6e !important; border-radius:8px !important;
    font-weight:600 !important;
  }
  .stButton > button:hover {
    background:#1e3a6e !important; border-color:#38bdf8 !important;
  }

  /* File uploader */
  .stFileUploader { background:#0f2044 !important; border-color:#1e3a6e !important; }

  /* Alerts / info */
  .stAlert { background:#0f2044 !important; border-color:#1e3a6e !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  FUNÇÕES DE COLETA
# ══════════════════════════════════════════════════════════════════
HDRS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

def _safe(v):
    if v is None: return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except: return None

@st.cache_data(ttl=1800, show_spinner=False)
def bcb_sgs(serie_id, data_inicio="01/01/2020"):
    hoje = datetime.today().strftime("%d/%m/%Y")
    di   = data_inicio.replace("/", "%2F")
    df_  = hoje.replace("/", "%2F")
    url  = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie_id}/dados"
            f"?formato=json&dataInicial={di}&dataFinal={df_}")
    try:
        r = requests.get(url, headers=HDRS, timeout=30)
        r.raise_for_status()
        dados = r.json()
        if not dados: return None
        df = pd.DataFrame(dados)
        df["data"]  = pd.to_datetime(df["data"], dayfirst=True)
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        return df.dropna().sort_values("data").reset_index(drop=True)
    except:
        return None

@st.cache_data(ttl=1800, show_spinner=False)
def yf_hist(symbol, start="2020-01-01"):
    try:
        tk = yf.Ticker(symbol)
        df = tk.history(start=start, end=datetime.today().strftime("%Y-%m-%d"),
                        interval="1d", auto_adjust=True)
        if df.empty: return None
        df.index = df.index.tz_localize(None)
        return df[df["Close"].notna()].copy()
    except:
        return None

@st.cache_data(ttl=120, show_spinner=False)
def yf_info(symbol):
    """
    Busca preço em tempo real via fast_info (cotação atual do pregão)
    + histórico para calcular variações e 52s hi/lo.
    Cache de 2 minutos para refletir o mercado ao vivo.
    """
    try:
        tk = yf.Ticker(symbol)

        # fast_info traz o preço atual do pregão (não só fechamento)
        fi = tk.fast_info
        p  = _safe(fi.last_price) or _safe(fi.regular_market_price)
        pr = _safe(fi.previous_close)

        # Fallback: se fast_info não retornar, usar histórico
        if not p:
            df = yf_hist(symbol)
            if df is None or df.empty: return {}
            c  = df["Close"].dropna()
            p  = float(c.iloc[-1])
            pr = float(c.iloc[-2]) if len(c) > 1 else p

        if not pr or pr == 0:
            df = yf_hist(symbol)
            if df is not None and not df.empty:
                pr = float(df["Close"].dropna().iloc[-2])

        chg = (p - pr) / pr * 100 if pr else 0

        # Histórico para variações e 52s (cache longo, não muda com frequência)
        df = yf_hist(symbol)
        if df is None or df.empty:
            return {"price": p, "chg": chg, "prev": pr,
                    "chg_1m": None, "chg_ytd": None,
                    "hi52": None, "lo52": None}

        c = df["Close"].dropna()

        # Variação 1 mês
        p1m = float(c.iloc[-22]) if len(c) >= 22 else None

        # Variação no ano (YTD) — primeiro fechamento do ano atual
        df_ytd = df[df.index.year == datetime.today().year]
        p_ytd  = float(df_ytd["Close"].iloc[0]) if not df_ytd.empty else float(c.iloc[0])

        return {
            "price":    p,
            "chg":      chg,
            "prev":     pr,
            "chg_1m":   (p / p1m  - 1) * 100 if p1m  else None,
            "chg_ytd":  (p / p_ytd - 1) * 100 if p_ytd else None,
            "hi52":     float(c.tail(252).max()),
            "lo52":     float(c.tail(252).min()),
        }
    except Exception:
        return {}

@st.cache_data(ttl=1800, show_spinner=False)
def get_cpi():
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/datasets/cpi-us/master/data/cpiai.csv",
            headers=HDRS, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        df["data"] = pd.to_datetime(df["Date"])
        df["idx"]  = pd.to_numeric(df["Index"], errors="coerce")
        df = df[["data","idx"]].dropna().sort_values("data").reset_index(drop=True)
        df["valor"] = df["idx"].pct_change(12) * 100
        return df[["data","valor"]].dropna()[df["data"] >= "2020-01-01"].reset_index(drop=True)
    except:
        return None

def gerar_analise(ticker, nome, info):
    """Chama a API do Claude para gerar análise da ação com dados em tempo real."""
    try:
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return "⚠️ Chave API não configurada. Adicione ANTHROPIC_API_KEY nos Secrets do Streamlit Cloud (Settings → Secrets)."

        preco   = f"R$ {info['price']:,.2f}"   if info else "indisponível"
        var_dia = f"{info['chg']:+.2f}%"       if info else "indisponível"
        var_1m  = f"{info['chg_1m']:+.2f}%"    if info and info.get('chg_1m') else "indisponível"
        var_ano = f"{info['chg_ytd']:+.2f}%"   if info else "indisponível"
        hi52    = f"R$ {info['hi52']:,.2f}"     if info else "indisponível"
        lo52    = f"R$ {info['lo52']:,.2f}"     if info else "indisponível"

        prompt = f"""Você é um analista de investimentos experiente focado no mercado brasileiro.
Gere uma análise concisa e objetiva sobre a ação {ticker} ({nome}) com base nos dados abaixo e no seu conhecimento.

DADOS ATUAIS DE MERCADO:
- Preço atual: {preco}
- Variação dia: {var_dia}
- Variação 1 mês: {var_1m}
- Variação no ano: {var_ano}
- Máxima 52 semanas: {hi52}
- Mínima 52 semanas: {lo52}

Estruture a análise com estas seções (use markdown com negrito e emojis):

**📊 Momento da Ação**
Análise técnica e de preço baseada nos dados acima (2-3 linhas).

**🏢 Momento da Empresa**
Fundamentos recentes, resultados e posição competitiva (2-3 linhas).

**🏭 Momento do Setor**
Contexto do setor no Brasil e perspectivas (2-3 linhas).

**⚠️ Principais Riscos**
Lista com 3 riscos relevantes.

**🚀 Potencial de Crescimento**
Catalisadores e perspectivas segundo analistas (2-3 linhas).

Seja direto e profissional. Ao final, adicione uma linha: *Esta análise é educacional e não constitui recomendação de investimento.*"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    except Exception as e:
        return f"Erro ao gerar análise: {str(e)}"


@st.cache_data(ttl=300, show_spinner=False)
def get_noticias():
    feeds = [
        ("InfoMoney",       "https://www.infomoney.com.br/feed/"),
        ("Valor Econômico", "https://valor.globo.com/rss/todosostemas"),
        ("Reuters BR",      "https://feeds.reuters.com/reuters/BRbusinessNews"),
        ("Exame",           "https://exame.com/feed/"),
    ]
    items = []
    for source, url in feeds:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:6]:
                desc = getattr(e, "summary", "") or ""
                # strip HTML tags
                import re
                desc = re.sub(r"<[^>]+>", "", desc)[:180]
                items.append({
                    "source": source,
                    "title":  e.get("title", ""),
                    "link":   e.get("link", "#"),
                    "desc":   desc,
                    "date":   e.get("published", ""),
                })
        except:
            pass
    return items

# ══════════════════════════════════════════════════════════════════
#  HELPERS DE GRÁFICO
# ══════════════════════════════════════════════════════════════════
DARK_LAY = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
              size=11, color="#94a3b8"),
    xaxis=dict(gridcolor="rgba(255,255,255,.06)", linecolor="rgba(255,255,255,.1)",
               tickfont=dict(size=10, color="#64748b")),
    yaxis=dict(gridcolor="rgba(255,255,255,.06)", linecolor="rgba(255,255,255,.1)",
               tickfont=dict(size=10, color="#64748b"), zeroline=False),
    legend=dict(bgcolor="rgba(10,22,40,.85)", bordercolor="rgba(56,189,248,.2)",
                borderwidth=1, font=dict(size=11, color="#94a3b8"),
                orientation="h", x=0, y=1.1),
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#060e1f", font=dict(color="#e2e8f5", size=11),
                    bordercolor="#38bdf8"),
    margin=dict(t=30, r=14, b=40, l=52),
)

def yax(**overrides):
    """Retorna dict de yaxis sem conflito de chaves — overrides sobrepõem DARK_LAY."""
    base = dict(DARK_LAY["yaxis"])
    base.update(overrides)
    return base

def xax(**overrides):
    base = dict(DARK_LAY["xaxis"])
    base.update(overrides)
    return base

def mk_fig(**kwargs):
    fig = go.Figure()
    lay = {**DARK_LAY, **kwargs}
    fig.update_layout(**lay)
    return fig

PLOTLY_CFG = {"displayModeBar": False, "responsive": True}

COLORS = {
    "blue":   "#38bdf8",
    "green":  "#4ade80",
    "purple": "#c084fc",
    "amber":  "#fbbf24",
    "red":    "#f87171",
    "teal":   "#2dd4bf",
    "slate":  "#94a3b8",
    "sky":    "#7dd3fc",
}

# Converte hex para rgba com alpha para usar como fillcolor
_HEX_FILL = {
    "#38bdf8": "rgba(56,189,248,0.08)",
    "#4ade80": "rgba(74,222,128,0.08)",
    "#c084fc": "rgba(192,132,252,0.08)",
    "#fbbf24": "rgba(251,191,36,0.08)",
    "#f87171": "rgba(248,113,113,0.08)",
    "#2dd4bf": "rgba(45,212,191,0.08)",
    "#94a3b8": "rgba(148,163,184,0.08)",
    "#7dd3fc": "rgba(125,211,252,0.08)",
}
def fill_color(hex_color):
    return _HEX_FILL.get(hex_color, "rgba(56,189,248,0.08)")

def render_table(rows):
    """Tabela HTML estilizada no tema escuro."""
    if not rows: return
    cols = list(rows[0].keys())
    right = {"Último","Dia","1M","Ano","Máx 52s","Mín 52s",
             "Estrangeiro","Institucional","Pessoa Física","Inst. Financeira",
             "Outros","Saldo","IBOVESPA"}

    def cell_style(val, col):
        align = "right" if col in right else "left"
        color = ""
        if isinstance(val, str):
            if val.startswith("▲"): color = "color:#4ade80;font-weight:600;"
            elif val.startswith("▼"): color = "color:#f87171;font-weight:600;"
        return f"padding:10px 14px;border-bottom:1px solid #1e3a6e;text-align:{align};font-size:12px;white-space:nowrap;{color}"

    th = "".join(
        f'<th style="background:#162554;color:#38bdf8;font-size:10px;font-weight:700;'+
        f'text-transform:uppercase;letter-spacing:.05em;padding:10px 14px;'+
        f'text-align:{"right" if c in right else "left"};white-space:nowrap;'+
        f'border-bottom:2px solid #1e3a6e">{c}</th>'
        for c in cols)

    trs = ""
    for i, row in enumerate(rows):
        bg = "#0f2044" if i % 2 == 0 else "#0a1832"
        tds = "".join(
            f'<td style="{cell_style(row.get(c,""), c)}">{row.get(c,"—")}</td>'
            for c in cols)
        trs += f'<tr style="background:{bg}">{tds}</tr>'

    st.markdown(
        f'<div style="overflow-x:auto;border-radius:10px;border:1px solid #1e3a6e;margin-bottom:16px">'+
        f'<table style="width:100%;border-collapse:collapse;font-family:-apple-system,sans-serif">'+
        f'<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>',
        unsafe_allow_html=True)

def line_trace(df, col, name, color, dash="solid"):
    if df is None or df.empty: return None
    return go.Scatter(
        x=df.index, y=df[col], name=name, mode="lines",
        line=dict(color=color, width=2, dash=dash),
        hovertemplate=f"%{{y:.2f}}<extra>{name}</extra>",
    )

def area_trace(df, col, name, color):
    if df is None or df.empty: return None
    return go.Scatter(
        x=df.index, y=df[col], name=name, mode="lines", fill="tozeroy",
        line=dict(color=color, width=2),
        fillcolor=color.replace("rgb(", "rgba(").replace(")", ",0.08)") if "rgb(" in color
                  else "rgba(56,189,248,0.08)",
        hovertemplate=f"%{{y:.2f}}<extra>{name}</extra>",
    )

def b100(df):
    if df is None or df.empty: return None
    s = df["Close"].dropna()
    if s.empty or s.iloc[0] == 0: return None
    return (s / s.iloc[0] * 100)

def fmt(v, dec=2, pre=""):
    if v is None: return "—"
    return f"{pre}{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fp(v):
    if v is None: return "—"
    return ("+" if v >= 0 else "") + f"{v:.2f}%"

def mcard(label, sym):
    info = yf_info(sym)
    if not info:
        st.markdown(f"""<div class="mcard">
            <div class="mcard-label">{label}</div>
            <div class="mcard-val">—</div>
            <div class="mcard-neu">sem dados</div></div>""", unsafe_allow_html=True)
        return
    p = info["price"]; chg = info["chg"]
    cls = "mcard-up" if chg >= 0 else "mcard-dn"
    arr = "▲" if chg >= 0 else "▼"
    st.markdown(f"""<div class="mcard">
        <div class="mcard-label">{label}</div>
        <div class="mcard-val">{fmt(p)}</div>
        <div class="{cls}">{arr} {fp(chg)}</div></div>""", unsafe_allow_html=True)

def tbl_row(sym, nome, dec=2, pre=""):
    info = yf_info(sym)
    if not info: return {"Ativo": nome, "Último": "—", "Dia": "—", "1M": "—", "Ano": "—"}
    p = info["price"]
    def pill(v):
        if v is None: return "—"
        return f"{'▲' if v>=0 else '▼'} {abs(v):.2f}%"
    return {
        "Ativo": nome,
        "Último": fmt(p, dec, pre),
        "Dia":    pill(info["chg"]),
        "1M":     pill(info.get("chg_1m")),
        "Ano":    pill(info.get("chg_ytd")),
        "Máx 52s": fmt(info["hi52"], dec, pre),
        "Mín 52s": fmt(info["lo52"], dec, pre),
    }

# ══════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════
now = datetime.now()
ts  = now.strftime("%d/%m/%Y às %H:%M")
st.markdown(f"""
<div class="painel-header">
  <div>
    <span class="pulse"></span>
    <span class="painel-title">Painel Macro Brasil</span>
  </div>
  <div class="painel-ts">🕐 {ts} (Brasília) &nbsp;·&nbsp; Yahoo Finance · BCB · BLS</div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
#  ABAS
# ══════════════════════════════════════════════════════════════════
tabs = st.tabs(["Resumo", "Bolsa", "Câmbio", "Commodities",
                "Juros", "Inflação", "Fluxo B3", "📰 Notícias", "📈 Ações", "🔗 Links"])

# ─────────────────────────────────────────────────────────────────
# ABA 1: RESUMO
# ─────────────────────────────────────────────────────────────────
with tabs[0]:
    st.markdown("#### Bolsa")
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: mcard("IBOVESPA", "^BVSP")
    with c2: mcard("S&P 500",  "^GSPC")
    with c3: mcard("Nasdaq 100","^NDX")
    with c4: mcard("VIX",      "^VIX")
    with c5: mcard("Dow Jones","^DJI")

    st.markdown("#### Câmbio e Cripto")
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: mcard("USD/BRL",   "BRL=X")
    with c2: mcard("EUR/BRL",   "EURBRL=X")
    with c3: mcard("DXY",       "DX-Y.NYB")
    with c4: mcard("Bitcoin",   "BTC-USD")
    with c5: mcard("Ethereum",  "ETH-USD")

    st.markdown("#### Commodities")
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: mcard("WTI",        "CL=F")
    with c2: mcard("Brent",      "BZ=F")
    with c3: mcard("Ouro",       "GC=F")
    with c4: mcard("Minério Fe", "TIO=F")
    with c5: mcard("Cobre",      "HG=F")

    # Gráficos
    c1, c2 = st.columns(2)
    with c1:
        ibovB = b100(yf_hist("^BVSP"))
        spB   = b100(yf_hist("^GSPC"))
        ndxB  = b100(yf_hist("^NDX"))
        fig   = mk_fig(height=260)
        if ibovB is not None: fig.add_trace(go.Scatter(x=ibovB.index, y=ibovB, name="IBOVESPA", mode="lines", line=dict(color=COLORS["blue"],  width=2)))
        if spB   is not None: fig.add_trace(go.Scatter(x=spB.index,   y=spB,   name="S&P 500",  mode="lines", line=dict(color=COLORS["green"], width=2, dash="dash")))
        if ndxB  is not None: fig.add_trace(go.Scatter(x=ndxB.index,  y=ndxB,  name="Nasdaq",   mode="lines", line=dict(color=COLORS["purple"],width=2, dash="dot")))
        st.markdown("**Retorno base 100**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with c2:
        usd = yf_hist("BRL=X")
        fig = mk_fig(height=260)
        if usd is not None: fig.add_trace(go.Scatter(x=usd.index, y=usd["Close"], name="USD/BRL", mode="lines", fill="tozeroy", line=dict(color=COLORS["amber"], width=2), fillcolor="rgba(251,191,36,0.08)"))
        st.markdown("**USD/BRL**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    c1, c2 = st.columns(2)
    with c1:
        sel = bcb_sgs(432); t10 = yf_hist("^TNX")
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if sel is not None: fig.add_trace(go.Scatter(x=sel["data"], y=sel["valor"], name="Selic BR", mode="lines", line=dict(color=COLORS["red"], width=2)))
        if t10 is not None: fig.add_trace(go.Scatter(x=t10.index,  y=t10["Close"], name="T-10Y EUA", mode="lines", line=dict(color=COLORS["blue"], width=2, dash="dash")))
        st.markdown("**Selic vs Treasury 10Y**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with c2:
        ouro = yf_hist("GC=F"); wti = yf_hist("CL=F")
        fig = mk_fig(height=260)
        if ouro is not None: fig.add_trace(go.Scatter(x=ouro.index, y=ouro["Close"], name="Ouro", mode="lines", line=dict(color=COLORS["amber"], width=2)))
        if wti  is not None: fig.add_trace(go.Scatter(x=wti.index,  y=wti["Close"],  name="WTI",  mode="lines", line=dict(color=COLORS["slate"], width=2, dash="dash")))
        st.markdown("**Ouro e Petróleo WTI**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

# ─────────────────────────────────────────────────────────────────
# ABA 2: BOLSA
# ─────────────────────────────────────────────────────────────────
with tabs[1]:
    c1, c2 = st.columns(2)
    with c1:
        ibovB = b100(yf_hist("^BVSP"))
        spB   = b100(yf_hist("^GSPC"))
        ndxB  = b100(yf_hist("^NDX"))
        fig = mk_fig(height=340)
        if ibovB is not None: fig.add_trace(go.Scatter(x=ibovB.index, y=ibovB, name="IBOVESPA", mode="lines", line=dict(color=COLORS["blue"],   width=2)))
        if spB   is not None: fig.add_trace(go.Scatter(x=spB.index,   y=spB,   name="S&P 500",  mode="lines", line=dict(color=COLORS["green"],  width=2, dash="dash")))
        if ndxB  is not None: fig.add_trace(go.Scatter(x=ndxB.index,  y=ndxB,  name="Nasdaq",   mode="lines", line=dict(color=COLORS["purple"], width=2, dash="dot")))
        st.markdown("**Base 100**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with c2:
        vix = yf_hist("^VIX")
        fig = mk_fig(height=340)
        if vix is not None:
            fig.add_trace(go.Scatter(x=vix.index, y=vix["Close"], name="VIX", mode="lines", fill="tozeroy", line=dict(color=COLORS["red"], width=2), fillcolor="rgba(248,113,113,0.08)"))
            fig.add_hline(y=30, line=dict(color=COLORS["amber"], dash="dash", width=1.5), annotation_text="Zona stress")
        st.markdown("**VIX**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    # ── Heatmaps: IBOV e S&P 500 lado a lado ────────────────────────
    def make_heatmap(symbol, title):
        df_hm = yf_hist(symbol)
        if df_hm is None: return None
        d2 = df_hm[["Close"]].copy()
        d2["ret"] = d2["Close"].pct_change() * 100
        tbl = d2.groupby([d2.index.year, d2.index.month])["ret"].sum().round(2).unstack()
        tbl.columns = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
        fig = go.Figure(go.Heatmap(
            z=tbl.values, x=tbl.columns.tolist(), y=tbl.index.tolist(),
            colorscale=[[0,"#ef4444"],[0.45,"#1e293b"],[0.5,"#0f2044"],[0.55,"#14532d"],[1,"#4ade80"]],
            zmid=0, showscale=False,
            text=[[f"{v:.1f}%" if not math.isnan(v) else "" for v in row] for row in tbl.values],
            texttemplate="%{text}", textfont=dict(size=9, color="#e2e8f5"),
        ))
        fig.update_layout(**{**DARK_LAY, "height":max(180, len(tbl)*22+60), "title":dict(text=title, font=dict(color="#94a3b8", size=13)),
                             "yaxis": dict(autorange="reversed", tickfont=dict(size=10, color="#64748b"))})
        return fig

    hm_c1, hm_c2 = st.columns(2)
    with hm_c1:
        fig = make_heatmap("^BVSP", "Heatmap IBOVESPA — retornos mensais (%)")
        if fig: st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with hm_c2:
        fig = make_heatmap("^GSPC", "Heatmap S&P 500 — retornos mensais (%)")
        if fig: st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    # Tabela
    st.markdown("**Resumo**")
    rows = [tbl_row(s,n) for s,n in [("^BVSP","IBOVESPA"),("^GSPC","S&P 500"),("^NDX","Nasdaq 100"),("^VIX","VIX"),("^DJI","Dow Jones")]]
    render_table(rows)

# ─────────────────────────────────────────────────────────────────
# ABA 3: CÂMBIO
# ─────────────────────────────────────────────────────────────────
with tabs[2]:
    c1, c2 = st.columns(2)
    pairs = [("BRL=X","USD/BRL",COLORS["amber"]),("EURBRL=X","EUR/BRL",COLORS["teal"]),
             ("DX-Y.NYB","DXY",COLORS["slate"]),("BTC-USD","Bitcoin (USD)",COLORS["amber"])]
    for i,(sym,nome,cor) in enumerate(pairs):
        with [c1,c2,c1,c2][i]:
            df = yf_hist(sym)
            fig = mk_fig(height=250)
            if df is not None:
                fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name=nome, mode="lines",
                    fill="tozeroy", line=dict(color=cor, width=2), fillcolor=fill_color(cor)))
            st.markdown(f"**{nome}**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    st.markdown("**Resumo**")
    rows = [tbl_row(s,n,d,p) for s,n,d,p in [
        ("BRL=X","USD/BRL",4,"R$ "),("EURBRL=X","EUR/BRL",4,"R$ "),
        ("DX-Y.NYB","DXY",2,""),("BTC-USD","Bitcoin",0,"US$ "),("ETH-USD","Ethereum",2,"US$ ")]]
    render_table(rows)

# ─────────────────────────────────────────────────────────────────
# ABA 4: COMMODITIES
# ─────────────────────────────────────────────────────────────────
with tabs[3]:
    comms = [("CL=F","Petróleo WTI",COLORS["slate"]),("GC=F","Ouro",COLORS["amber"]),
             ("TIO=F","Minério de Ferro",COLORS["teal"]),("ZS=F","Soja",COLORS["green"])]
    c1, c2 = st.columns(2)
    for i,(sym,nome,cor) in enumerate(comms):
        with [c1,c2,c1,c2][i]:
            df = yf_hist(sym)
            fig = mk_fig(height=250)
            if df is not None:
                fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name=nome, mode="lines",
                    fill="tozeroy", line=dict(color=cor, width=2), fillcolor=fill_color(cor)))
            st.markdown(f"**{nome}**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    st.markdown("**Resumo**")
    rows = [tbl_row(s,n,d,"US$ ") for s,n,d in [
        ("CL=F","WTI",2),("BZ=F","Brent",2),("GC=F","Ouro",0),("SI=F","Prata",3),
        ("TIO=F","Minério",2),("ZS=F","Soja",2),("ZC=F","Milho",2),("HG=F","Cobre",3)]]
    render_table(rows)

# ─────────────────────────────────────────────────────────────────
# ABA 5: JUROS
# ─────────────────────────────────────────────────────────────────
with tabs[4]:
    sel  = bcb_sgs(432)
    t2y  = yf_hist("^IRX"); t5y = yf_hist("^FVX")
    t10y = yf_hist("^TNX"); t30y = yf_hist("^TYX")

    c1, c2 = st.columns(2)
    with c1:
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if sel is not None: fig.add_trace(go.Scatter(x=sel["data"], y=sel["valor"], name="Selic", mode="lines", fill="tozeroy", line=dict(color=COLORS["red"], width=2), fillcolor="rgba(248,113,113,0.08)"))
        st.markdown("**Selic Meta**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with c2:
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%", dtick=0.5))
        for df,nome,cor,dash in [(t2y,"T-2Y",COLORS["slate"],"dot"),(t5y,"T-5Y",COLORS["sky"],"solid"),(t10y,"T-10Y",COLORS["blue"],"solid"),(t30y,"T-30Y",COLORS["purple"],"dash")]:
            if df is not None: fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name=nome, mode="lines", line=dict(color=cor, width=2, dash=dash)))
        st.markdown("**Treasuries EUA**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    c1, c2 = st.columns(2)
    with c1:
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if sel  is not None: fig.add_trace(go.Scatter(x=sel["data"],  y=sel["valor"],   name="Selic BR", mode="lines", line=dict(color=COLORS["red"],  width=2)))
        if t10y is not None: fig.add_trace(go.Scatter(x=t10y.index, y=t10y["Close"],  name="T-10Y",    mode="lines", line=dict(color=COLORS["blue"], width=2, dash="dash")))
        st.markdown("**Selic vs T-10Y**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with c2:
        # Curva hoje
        pts = []
        for df,prazo in [(t2y,"2Y"),(t5y,"5Y"),(t10y,"10Y"),(t30y,"30Y")]:
            if df is not None and not df.empty:
                pts.append((prazo, float(df["Close"].dropna().iloc[-1])))
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if pts:
            fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts],
                mode="lines+markers", name="Curva hoje",
                line=dict(color=COLORS["purple"], width=2),
                marker=dict(size=9, color=COLORS["purple"])))
        st.markdown("**Curva de Juros EUA**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    # Spread 10Y - 2Y
    if t10y is not None and t2y is not None:
        merged = t10y[["Close"]].rename(columns={"Close":"t10"}).join(
                 t2y[["Close"]].rename(columns={"Close":"t2"}), how="inner")
        merged["spread"] = merged["t10"] - merged["t2"]
        fig = mk_fig(height=220, yaxis=yax(ticksuffix="%"))
        colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in merged["spread"]]
        fig.add_trace(go.Bar(x=merged.index, y=merged["spread"], name="Spread 10Y-2Y", marker_color=colors))
        st.markdown("**Spread 10Y − 2Y (inversão = possível recessão)**")
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

# ─────────────────────────────────────────────────────────────────
# ABA 6: INFLAÇÃO
# ─────────────────────────────────────────────────────────────────
with tabs[5]:
    ipca = bcb_sgs(13522); igpm = bcb_sgs(189); cpi = get_cpi()

    # IPCA 12m rolling
    d_ipca12 = None
    if ipca is not None and len(ipca) >= 12:
        vals = ipca["valor"].values
        a12v, a12d = [], []
        for i in range(11, len(vals)):
            a12v.append(round(((1 + vals[i-11:i+1]/100).prod()-1)*100, 2))
            a12d.append(ipca["data"].iloc[i])
        d_ipca12 = pd.DataFrame({"data": a12d, "valor": a12v})

    c1, c2 = st.columns(2)
    with c1:
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if d_ipca12 is not None:
            fig.add_trace(go.Scatter(x=d_ipca12["data"], y=d_ipca12["valor"], name="IPCA 12m",
                mode="lines", fill="tozeroy", line=dict(color=COLORS["red"], width=2),
                fillcolor="rgba(248,113,113,0.08)"))
        st.markdown("**IPCA acumulado 12 meses**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with c2:
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if ipca is not None:
            colors = [COLORS["red"] if v > 0 else COLORS["green"] for v in ipca["valor"]]
            fig.add_trace(go.Bar(x=ipca["data"], y=ipca["valor"], name="IPCA mensal", marker_color=colors))
        st.markdown("**IPCA mensal**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    c1, c2 = st.columns(2)
    with c1:
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if igpm is not None:
            colors = [COLORS["amber"] if v > 0 else COLORS["teal"] for v in igpm["valor"]]
            fig.add_trace(go.Bar(x=igpm["data"], y=igpm["valor"], name="IGP-M mensal", marker_color=colors))
        st.markdown("**IGP-M mensal**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)
    with c2:
        fig = mk_fig(height=260, yaxis=yax(ticksuffix="%"))
        if cpi is not None:
            colors = [COLORS["red"] if v > 3 else COLORS["amber"] if v > 2 else COLORS["green"] for v in cpi["valor"]]
            fig.add_trace(go.Bar(x=cpi["data"], y=cpi["valor"], name="CPI YoY %", marker_color=colors))
            if len(cpi) > 1:
                fig.add_hline(y=2, line=dict(color=COLORS["blue"], dash="dash", width=1.5), annotation_text="Meta Fed 2%")
        st.markdown("**CPI EUA — YoY %**"); st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

# ─────────────────────────────────────────────────────────────────
# ABA 7: FLUXO B3
# ─────────────────────────────────────────────────────────────────
with tabs[6]:
    st.info("📂 Faça upload do CSV de fluxo B3 (dadosdemercado.com.br/fluxo). "
            "Colunas: Data, Estrangeiro, Institucional, Pessoa física, Inst. Financeira, Outros")

    uploaded = st.file_uploader("Selecione o CSV", type="csv", label_visibility="collapsed")

    if uploaded:
        try:
            raw = uploaded.read().decode("utf-8")
            lines = raw.strip().split("\n")
            sep = ";" if lines[0].count(";") > lines[0].count(",") else ","

            def parse_val(s):
                s = s.replace('"','').strip()
                s = s.replace(" mi","").replace("mi","").strip()
                import re
                s = re.sub(r'\.(\d{3})(?=[,.]|$)', r'\1', s)
                s = s.replace(',','.')
                try: return float(s)
                except: return 0.0

            header = [h.replace('"','').strip().lower()
                      .replace('ã','a').replace('é','e').replace('í','i').replace(' ','_')
                      for h in lines[0].split(sep)]

            def fc(keys):
                return next((h for h in header if any(k in h for k in keys)), None)

            cD = fc(['data','date']); cE = fc(['estrang']); cI = fc(['instit'])
            cP = fc(['pessoa','fisic','pf']); cF = fc(['financ']); cO = fc(['outros'])

            rows = []
            for line in lines[1:]:
                vals = line.split(sep)
                obj  = {header[i]: (vals[i].replace('"','').strip() if i < len(vals) else '') for i in range(len(header))}
                if obj.get(cD): rows.append(obj)

            def parse_date(s):
                s = s.replace('"','').strip()
                if '/' in s:
                    p = s.split('/'); return f"{p[2]}-{p[1]}-{p[0]}"
                return s

            dates   = [parse_date(r[cD]) for r in rows]
            estrang = [parse_val(r[cE]) for r in rows]
            inst    = [parse_val(r[cI]) for r in rows]
            pf      = [parse_val(r[cP]) for r in rows]
            fin     = [parse_val(r.get(cF,'')) for r in rows]
            outros  = [parse_val(r.get(cO,'0')) for r in rows] if cO else [0]*len(rows)

            # Ordenar do mais antigo para mais recente
            ordem = sorted(range(len(dates)), key=lambda i: dates[i])
            dates   = [dates[i]   for i in ordem]
            estrang = [estrang[i] for i in ordem]
            inst    = [inst[i]    for i in ordem]
            pf      = [pf[i]      for i in ordem]
            fin     = [fin[i]     for i in ordem]
            outros  = [outros[i]  for i in ordem]

            # Agrupamento mensal
            def group_monthly(ds, vs):
                m = {}
                for d, v in zip(ds, vs):
                    k = d[:7]
                    m[k] = m.get(k, 0) + v
                keys = sorted(m.keys())
                return keys, [round(m[k],1) for k in keys]

            mE_x, mE_y = group_monthly(dates, estrang)
            mI_x, mI_y = group_monthly(dates, inst)
            mP_x, mP_y = group_monthly(dates, pf)
            mF_x, mF_y = group_monthly(dates, fin)
            mO_x, mO_y = group_monthly(dates, outros)

            c1, c2 = st.columns(2)
            with c1:
                fig = mk_fig(height=340, barmode="relative",
                             xaxis=xax(tickangle=-40),
                             yaxis=yax(ticksuffix=" M", zeroline=True,
                                        zerolinecolor="#374151", zerolinewidth=2,
                                        title=dict(text="R$ milhões")))
                fig.add_trace(go.Bar(x=mE_x, y=mE_y, name="Estrangeiro",     marker_color="rgba(56,189,248,.85)"))
                fig.add_trace(go.Bar(x=mI_x, y=mI_y, name="Institucional",   marker_color="rgba(74,222,128,.85)"))
                fig.add_trace(go.Bar(x=mP_x, y=mP_y, name="Pessoa Física",   marker_color="rgba(192,132,252,.85)"))
                fig.add_trace(go.Bar(x=mF_x, y=mF_y, name="Inst. Financeira",marker_color="rgba(251,191,36,.85)"))
                fig.add_trace(go.Bar(x=mO_x, y=mO_y, name="Outros",          marker_color="rgba(45,212,191,.85)"))
                st.markdown("**Fluxo mensal por tipo**")
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

            with c2:
                ibov_df = yf_hist("^BVSP")
                fig = mk_fig(height=300, xaxis=xax(type="date", dtick="M1", tickformat="%b/%Y", tickangle=-30))
                if ibov_df is not None:
                    d0, d1 = dates[0], dates[-1]
                    ibov_f = ibov_df[(ibov_df.index.strftime("%Y-%m-%d") >= d0) &
                                     (ibov_df.index.strftime("%Y-%m-%d") <= d1)]
                    if not ibov_f.empty:
                        fig.add_trace(go.Scatter(x=ibov_f.index, y=ibov_f["Close"],
                            name="IBOVESPA", mode="lines", fill="tozeroy",
                            line=dict(color=COLORS["blue"], width=2),
                            fillcolor="rgba(56,189,248,0.05)"))
                st.markdown("**IBOVESPA no período**")
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

            # Saldo total + acumulado
            soma = [estrang[i]+inst[i]+pf[i]+fin[i]+outros[i] for i in range(len(dates))]
            acum = []
            for v in soma: acum.append((acum[-1] if acum else 0) + v)

            c1, c2 = st.columns(2)
            with c1:
                fig = mk_fig(height=260, barmode="overlay",
                             yaxis=yax(ticksuffix=" M", zeroline=True, zerolinecolor="#374151"),
                             yaxis2=dict(overlaying="y", side="right", ticksuffix=" M",
                                         showgrid=False, zeroline=False,
                                         tickfont=dict(size=10, color="#64748b")))
                colors_soma = [COLORS["green"] if v >= 0 else COLORS["red"] for v in soma]
                fig.add_trace(go.Bar(x=dates, y=soma, name="Saldo diário", marker_color=["rgba(74,222,128,0.7)" if v>=0 else "rgba(248,113,113,0.7)" for v in soma]))
                fig.add_trace(go.Scatter(x=dates, y=acum, name="Acumulado", mode="lines",
                    line=dict(color=COLORS["blue"], width=2), yaxis="y2"))
                st.markdown("**Saldo total + Acumulado**")
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

            with c2:
                acum_e = []
                for v in estrang: acum_e.append((acum_e[-1] if acum_e else 0) + v)
                fig = mk_fig(height=260, barmode="overlay",
                             yaxis=yax(ticksuffix=" M", zeroline=True, zerolinecolor="#374151"),
                             yaxis2=dict(overlaying="y", side="right", ticksuffix=" M",
                                         showgrid=False, zeroline=False,
                                         tickfont=dict(size=10, color="#64748b")))
                colors_e = [COLORS["blue"] if v >= 0 else COLORS["red"] for v in estrang]
                fig.add_trace(go.Bar(x=dates, y=estrang, name="Estrangeiro diário", marker_color=["rgba(56,189,248,0.7)" if v>=0 else "rgba(248,113,113,0.7)" for v in estrang]))
                fig.add_trace(go.Scatter(x=dates, y=acum_e, name="Acumulado", mode="lines",
                    line=dict(color=COLORS["blue"], width=2), yaxis="y2"))
                st.markdown("**Fluxo Estrangeiro + Acumulado**")
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

            # Tabela
            st.markdown("**Tabela — últimas 100 sessões**")
            tbl_data = []
            ibov_map = {}
            if ibov_df is not None:
                for d, v in zip(ibov_df.index.strftime("%Y-%m-%d"), ibov_df["Close"]):
                    ibov_map[d] = round(float(v), 0)
            for i in range(len(dates)-1, max(-1, len(dates)-101), -1):
                d = dates[i]
                s = estrang[i]+inst[i]+pf[i]+fin[i]+outros[i]
                tbl_data.append({
                    "Data": d,
                    "Estrangeiro": f"{estrang[i]:+.1f}",
                    "Institucional": f"{inst[i]:+.1f}",
                    "Pessoa Física": f"{pf[i]:+.1f}",
                    "Inst. Financeira": f"{fin[i]:+.1f}",
                    "Outros": f"{outros[i]:+.1f}",
                    "Saldo": f"{s:+.1f}",
                    "IBOVESPA": f"{ibov_map.get(d, '—'):.0f}" if d in ibov_map else "—",
                })
            render_table(tbl_data)

        except Exception as e:
            st.error(f"Erro ao processar CSV: {e}")

# ─────────────────────────────────────────────────────────────────
# ABA 8: NOTÍCIAS
# ─────────────────────────────────────────────────────────────────
with tabs[7]:
    with st.spinner("Carregando notícias..."):
        noticias = get_noticias()

    # Cabeçalho com stats e botão de refresh
    h1, h2 = st.columns([4,1])
    with h1:
        if noticias:
            st.markdown(f'<p style="color:#64748b;font-size:12px;margin:0 0 16px">'
                        f'📡 {len(noticias)} notícias carregadas · {ts}</p>',
                        unsafe_allow_html=True)
    with h2:
        if st.button("🔄 Atualizar", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    if not noticias:
        st.markdown('''<div style="background:#0f2044;border:1px solid #f87171;border-radius:10px;
            padding:16px 20px;color:#f87171;margin-bottom:16px">
            ⚠️ Não foi possível carregar as notícias. Verifique sua conexão.</div>''',
            unsafe_allow_html=True)
        st.markdown("**Acesso direto aos portais:**")
        links_col1, links_col2 = st.columns(2)
        with links_col1:
            for nome, url in [("InfoMoney","https://www.infomoney.com.br"),
                               ("Valor Econômico","https://valor.globo.com")]:
                st.markdown(f'[🔗 {nome}]({url})')
        with links_col2:
            for nome, url in [("Reuters Brasil","https://br.reuters.com"),
                               ("Exame","https://exame.com")]:
                st.markdown(f'[🔗 {nome}]({url})')
    else:
        # Filtros em linha
        fontes  = sorted(set(n["source"] for n in noticias))
        f1, f2  = st.columns([3,1])
        with f1:
            sel_fontes = st.multiselect("Filtrar por fonte:", fontes, default=fontes,
                                        label_visibility="collapsed")
        with f2:
            busca = st.text_input("🔍 Buscar", placeholder="palavra-chave...",
                                  label_visibility="collapsed")

        filtradas = [n for n in noticias
                     if n["source"] in sel_fontes
                     and (not busca or busca.lower() in n["title"].lower()
                          or busca.lower() in n["desc"].lower())]

        if not filtradas:
            st.info("Nenhuma notícia encontrada com os filtros selecionados.")
        else:
            # Grade: 2 colunas de cards
            for i in range(0, len(filtradas), 2):
                gc1, gc2 = st.columns(2)
                for col, idx in [(gc1, i), (gc2, i+1)]:
                    if idx >= len(filtradas): break
                    n = filtradas[idx]
                    source_colors = {
                        "InfoMoney":       "#38bdf8",
                        "Valor Econômico": "#4ade80",
                        "Reuters BR":      "#f87171",
                        "Exame":           "#c084fc",
                    }
                    cor = source_colors.get(n["source"], "#94a3b8")
                    with col:
                        st.markdown(f'''
<div style="background:linear-gradient(135deg,#0f2044 0%,#0d1a38 100%);
     border:1px solid {cor}44;border-left:4px solid {cor};
     border-radius:12px;padding:22px 24px;margin-bottom:16px;
     box-shadow:0 4px 20px rgba(0,0,0,.5);
     display:flex;flex-direction:column;min-height:240px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
    <span style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;
          color:{cor};background:{cor}25;padding:4px 12px;border-radius:20px;
          border:1px solid {cor}55">
      {n["source"]}
    </span>
    <span style="font-size:11px;color:#4a5568">
      🕐 {n["date"][:16] if n["date"] else ""}
    </span>
  </div>
  <a href="{n["link"]}" target="_blank"
     style="font-size:18px;font-weight:800;color:#f8fafc;text-decoration:none;
            line-height:1.45;display:block;margin-bottom:12px;letter-spacing:-.02em;
            flex-grow:0">
    {n["title"]}
  </a>
  <div style="width:48px;height:3px;background:{cor};border-radius:2px;margin-bottom:12px"></div>
  <p style="font-size:13px;color:#94a3b8;line-height:1.7;margin:0 0 16px;flex-grow:1">
    {n["desc"]}
  </p>
  <a href="{n["link"]}" target="_blank"
     style="font-size:12px;color:{cor};font-weight:700;text-decoration:none;
            display:inline-flex;align-items:center;gap:5px;
            background:{cor}18;padding:6px 14px;border-radius:6px;
            border:1px solid {cor}44;align-self:flex-start">
    Ler matéria completa ↗
  </a>
</div>''', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# ABA 9: AÇÕES B3
# ─────────────────────────────────────────────────────────────────
with tabs[8]:

    ACOES_B3 = [
        # (ticker,    nome completo,         cor)
        ("WEGE3.SA",  "WEG",                 COLORS["blue"]),
        ("BPAC11.SA", "BTG Pactual",         COLORS["teal"]),
        ("VALE3.SA",  "Vale",                COLORS["amber"]),
        ("GGBR4.SA",  "Gerdau",             COLORS["red"]),
        ("BBAS3.SA",  "Banco do Brasil",     COLORS["green"]),
        ("PETR4.SA",  "Petrobras",           COLORS["purple"]),
        ("ITUB4.SA",  "Itaú Unibanco",       COLORS["sky"]),
        ("ABEV3.SA",  "Ambev",               COLORS["amber"]),
        ("RENT3.SA",  "Localiza",            COLORS["teal"]),
        ("SUZB3.SA",  "Suzano",              COLORS["green"]),
        ("RADL3.SA",  "Raia Drogasil",       COLORS["blue"]),
        ("MGLU3.SA",  "Magazine Luiza",      COLORS["red"]),
        ("EGIE3.SA",  "Engie Brasil",        COLORS["purple"]),
        ("TOTS3.SA",  "Totvs",               COLORS["sky"]),
        ("LREN3.SA",  "Lojas Renner",        COLORS["amber"]),
    ]

    start_5y = (datetime.now() - timedelta(days=365*5)).strftime("%Y-%m-%d")

    @st.cache_data(ttl=1800, show_spinner=False)
    def acao_hist(ticker):
        return yf_hist(ticker, start=start_5y)

    # ── Cards de preço no topo ────────────────────────────────────
    st.markdown("#### Cotações atuais")
    st.markdown(
        '<p style="font-size:12px;color:#4a5568;margin:0 0 12px">'
        '💡 Clique em <strong style="color:#38bdf8">🤖 Análise IA</strong> '
        'em qualquer ação para gerar uma análise com Claude.</p>',
        unsafe_allow_html=True
    )

    # Estado para controlar qual ação está com análise aberta
    if "analise_ticker" not in st.session_state:
        st.session_state.analise_ticker = None
    if "analise_texto" not in st.session_state:
        st.session_state.analise_texto = {}

    cols_cards = st.columns(5)
    for i, (ticker, nome, cor) in enumerate(ACOES_B3):
        info = yf_info(ticker)
        with cols_cards[i % 5]:
            if info:
                p         = info["price"]
                chg       = info["chg"]
                arrow     = "▲" if chg >= 0 else "▼"
                color_chg = "#4ade80" if chg >= 0 else "#f87171"
                st.markdown(f'''
<div style="background:#0f2044;border:1px solid #1e3a6e;border-top:3px solid {cor};
     border-radius:10px;padding:12px 14px;margin-bottom:4px">
  <div style="font-size:10px;color:#64748b;font-weight:700;
       text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">
    {ticker.replace(".SA","")}
  </div>
  <div style="font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:6px">{nome}</div>
  <div style="font-size:19px;font-weight:800;color:#e2e8f5;letter-spacing:-.02em">
    R$ {p:,.2f}
  </div>
  <div style="font-size:12px;font-weight:600;color:{color_chg};margin-top:3px">
    {arrow} {abs(chg):.2f}%
  </div>
</div>''', unsafe_allow_html=True)
            else:
                st.markdown(f'''
<div style="background:#0f2044;border:1px solid #1e3a6e;border-top:3px solid {cor};
     border-radius:10px;padding:12px 14px;margin-bottom:4px">
  <div style="font-size:10px;color:#64748b;font-weight:700;
       text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">
    {ticker.replace(".SA","")}
  </div>
  <div style="font-size:12px;color:#4a5568">{nome}</div>
  <div style="font-size:12px;color:#4a5568;margin-top:6px">sem dados</div>
</div>''', unsafe_allow_html=True)

            # Botão de análise IA
            btn_label = "⏳ Analisando..." if st.session_state.analise_ticker == ticker else "🤖 Análise IA"
            if st.button(btn_label, key=f"btn_{ticker}",
                         use_container_width=True,
                         disabled=(st.session_state.analise_ticker == ticker)):
                st.session_state.analise_ticker = ticker
                if ticker not in st.session_state.analise_texto:
                    with st.spinner(f"Gerando análise de {nome}..."):
                        st.session_state.analise_texto[ticker] = gerar_analise(ticker, nome, info)
                st.rerun()

        # Quebra de linha a cada 5
        if (i+1) % 5 == 0 and i+1 < len(ACOES_B3):
            cols_cards = st.columns(5)

    # ── Painel de análise (abaixo dos cards) ─────────────────────
    if st.session_state.analise_ticker:
        ticker_sel = st.session_state.analise_ticker
        nome_sel   = next((n for t,n,_ in ACOES_B3 if t == ticker_sel), ticker_sel)
        cor_sel    = next((c for t,_,c in ACOES_B3 if t == ticker_sel), COLORS["blue"])
        texto      = st.session_state.analise_texto.get(ticker_sel, "")

        st.markdown(
            f'<div style="background:linear-gradient(135deg,#0f2044,#0d1a38);'+
            f'border:1px solid {cor_sel}44;border-left:4px solid {cor_sel};'+
            f'border-radius:12px;padding:20px 24px;margin:16px 0">'+
            f'<div style="display:flex;align-items:center;justify-content:space-between;'+
            f'margin-bottom:4px">'+
            f'<h4 style="color:{cor_sel};margin:0;font-size:15px">🤖 Análise IA — '+
            f'{ticker_sel.replace(".SA","")} · {nome_sel}</h4>'+
            f'<span style="font-size:11px;color:#4a5568">⚠️ Não é recomendação de investimento</span>'+
            f'</div></div>',
            unsafe_allow_html=True
        )
        st.markdown(texto)

        col_nova, col_fechar = st.columns([1, 4])
        with col_nova:
            if st.button("🔄 Nova análise", key="nova_analise"):
                st.session_state.analise_texto.pop(ticker_sel, None)
                with st.spinner("Gerando nova análise..."):
                    st.session_state.analise_texto[ticker_sel] = gerar_analise(
                        ticker_sel, nome_sel, yf_info(ticker_sel))
                st.rerun()
        with col_fechar:
            if st.button("✕ Fechar análise", key="fechar_analise"):
                st.session_state.analise_ticker = None
                st.rerun()

        st.markdown("---")

    st.markdown("---")

    # ── Seletor de ação para gráfico detalhado ────────────────────
    st.markdown("#### Gráfico detalhado — 5 anos")
    ticker_names = {t: f"{t.replace('.SA','')} — {n}" for t,n,_ in ACOES_B3}
    sel_ticker = st.selectbox(
        "Selecione a ação:",
        options=[t for t,_,_ in ACOES_B3],
        format_func=lambda x: ticker_names[x],
        label_visibility="collapsed"
    )
    sel_nome = next(n for t,n,_ in ACOES_B3 if t == sel_ticker)
    sel_cor  = next(c for t,_,c in ACOES_B3 if t == sel_ticker)

    df_sel = acao_hist(sel_ticker)
    if df_sel is not None and not df_sel.empty:
        info = yf_info(sel_ticker)
        # Métricas rápidas
        m1, m2, m3, m4, m5 = st.columns(5)
        metrics = [
            ("Preço atual",  f"R$ {info['price']:,.2f}" if info else "—"),
            ("Var. dia",     f"{info['chg']:+.2f}%" if info else "—"),
            ("Var. 1M",      f"{info['chg_1m']:+.2f}%" if info and info.get('chg_1m') else "—"),
            ("Var. ano",     f"{info['chg_ytd']:+.2f}%" if info else "—"),
            ("Máx 52s",      f"R$ {info['hi52']:,.2f}" if info else "—"),
        ]
        for col, (label, val) in zip([m1,m2,m3,m4,m5], metrics):
            with col:
                st.metric(label, val)

        # Gráfico de preço
        fig = mk_fig(height=380,
                     yaxis=yax(tickprefix="R$ ", tickformat=",.2f"),
                     xaxis=xax())
        fig.add_trace(go.Scatter(
            x=df_sel.index, y=df_sel["Close"],
            name=sel_nome, mode="lines",
            line=dict(color=sel_cor, width=2.5),
            fill="tozeroy", fillcolor=fill_color(sel_cor),
            hovertemplate="R$ %{y:,.2f}<extra></extra>"
        ))
        # Média móvel 200 dias
        ma200 = df_sel["Close"].rolling(200).mean()
        fig.add_trace(go.Scatter(
            x=df_sel.index, y=ma200,
            name="MM 200",
            mode="lines", line=dict(color="#475569", width=1.5, dash="dash"),
            hovertemplate="MM200: R$ %{y:,.2f}<extra></extra>"
        ))
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

        # Volume
        fig_vol = mk_fig(height=120, margin=dict(t=5, r=14, b=30, l=52),
                         yaxis=yax(tickformat=".2s", title=dict(text="Volume")),
                         xaxis=xax(), showlegend=False)
        vol_colors = [fill_color(sel_cor) if c >= o else "rgba(248,113,113,0.5)"
                      for c, o in zip(df_sel["Close"], df_sel["Open"])]
        fig_vol.add_trace(go.Bar(x=df_sel.index, y=df_sel["Volume"],
                                  marker_color=vol_colors, name="Volume"))
        st.plotly_chart(fig_vol, use_container_width=True, config=PLOTLY_CFG)
    else:
        st.info(f"Dados indisponíveis para {sel_ticker}")

    st.markdown("---")

    # ── Grade com todos os gráficos ───────────────────────────────
    st.markdown("#### Visão geral — todos os ativos (5 anos)")
    for i in range(0, len(ACOES_B3), 3):
        grupo = ACOES_B3[i:i+3]
        cols_g = st.columns(3)
        for col, (ticker, nome, cor) in zip(cols_g, grupo):
            with col:
                df_g = acao_hist(ticker)
                fig  = mk_fig(height=220,
                              margin=dict(t=30, r=10, b=30, l=50),
                              yaxis=yax(tickprefix="R$ ", tickformat=",.0f"),
                              xaxis=xax(),
                              showlegend=False,
                              title=dict(text=f"{ticker.replace('.SA','')} — {nome}",
                                         font=dict(size=12, color="#94a3b8"), x=0))
                if df_g is not None and not df_g.empty:
                    fig.add_trace(go.Scatter(
                        x=df_g.index, y=df_g["Close"],
                        mode="lines", line=dict(color=cor, width=1.8),
                        fill="tozeroy", fillcolor=fill_color(cor),
                        hovertemplate="R$ %{y:,.2f}<extra></extra>"
                    ))
                else:
                    fig.add_annotation(text="sem dados", x=0.5, y=0.5,
                                       xref="paper", yref="paper",
                                       showarrow=False, font=dict(color="#4a5568"))
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG)

    # ── Tabela comparativa ────────────────────────────────────────
    st.markdown("#### Tabela comparativa")
    tbl_acoes = []
    for ticker, nome, _ in ACOES_B3:
        info = yf_info(ticker)
        if info:
            tbl_acoes.append({
                "Ticker": ticker.replace(".SA",""),
                "Empresa": nome,
                "Último (R$)": f"{info['price']:,.2f}",
                "Dia":  ("▲ " if info["chg"] >= 0 else "▼ ") + f"{abs(info['chg']):.2f}%",
                "1M":   ("▲ " if (info.get("chg_1m") or 0) >= 0 else "▼ ") + f"{abs(info.get('chg_1m') or 0):.2f}%",
                "Ano":  ("▲ " if info["chg_ytd"] >= 0 else "▼ ") + f"{abs(info['chg_ytd']):.2f}%",
                "Máx 52s": f"{info['hi52']:,.2f}",
                "Mín 52s": f"{info['lo52']:,.2f}",
            })
        else:
            tbl_acoes.append({"Ticker": ticker.replace(".SA",""), "Empresa": nome,
                              "Último (R$)":"—","Dia":"—","1M":"—","Ano":"—","Máx 52s":"—","Mín 52s":"—"})
    render_table(tbl_acoes)




# ─────────────────────────────────────────────────────────────────
# ABA 10: LINKS
# ─────────────────────────────────────────────────────────────────
with tabs[9]:

    def render_link_card(title, links, cor):
        items_html = ""
        for nome, url in links:
            items_html += (
                f'<a href="{url}" target="_blank" '
                f'style="display:flex;align-items:center;gap:8px;padding:9px 2px;'
                f'border-bottom:1px solid #1e3a6e;color:#94a3b8;text-decoration:none;'
                f'font-size:13px">'
                f'<span style="color:{cor};font-size:11px;flex-shrink:0">↗</span>'
                f'{nome}</a>'
            )
        card = (
            f'<div style="background:#0f2044;border:1px solid #1e3a6e;'
            f'border-top:3px solid {cor};border-radius:12px;padding:18px 20px">'
            f'<h4 style="color:{cor};font-size:11px;font-weight:800;'
            f'text-transform:uppercase;letter-spacing:.08em;'
            f'margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid #1e3a6e">'
            f'{title}</h4>'
            f'{items_html}</div>'
        )
        st.markdown(card, unsafe_allow_html=True)

    st.markdown("#### 📅 Links do dia a dia")
    d1, d2, d3 = st.columns(3)
    with d1:
        render_link_card("Bolsa — Brasil", [
            ("Gráfico + Volume IBOV", "https://finance.yahoo.com/quote/%5EBVSP/"),
            ("Estrangeiro na bolsa",  "https://www.dadosdemercado.com.br/fluxo"),
        ], COLORS["blue"])
    with d2:
        render_link_card("Juros Futuros", [
            ("Curva de juros futuros BR", "https://br.tradingview.com/symbols/BMFBOVESPA-DI11!/forward-curve/"),
            ("Treasury 10 Anos",          "https://br.tradingview.com/chart/?symbol=TVC%3AUS10Y"),
            ("Treasury 30 Anos",          "https://br.tradingview.com/chart/?symbol=TVC%3AUS30Y"),
        ], COLORS["purple"])
    with d3:
        render_link_card("Câmbio & Outros", [
            ("DXY",                     "https://br.tradingview.com/symbols/TVC-DXY/"),
            ("USD/BRL",                 "https://www.google.com/search?q=usd/brl"),
            ("Leilões — LTN, LFT, NTN", "https://sisweb.tesouro.gov.br/apex/f?p=2691:2:::NO:::"),
            ("Gráfico S&P 500",         "https://www.google.com/search?q=s%26p500"),
        ], COLORS["amber"])

    st.markdown("---")
    st.markdown("#### 🌐 Links gerais")

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        render_link_card("Links Diários", [
            ("CDS Brasil 5Y",    "https://br.investing.com/rates-bonds/brazil-cds-5-years-usd-streaming-chart"),
            ("VIX",              "https://br.investing.com/indices/volatility-s-p-500"),
            ("VIX B3",           "https://br.investing.com/indices/s-p-b3-ibovespa-vix"),
            ("CDS EUA 10Y",      "https://br.investing.com/rates-bonds/united-states-cds-10-years-usd"),
            ("Petróleo (WTI)",   "https://br.investing.com/commodities/crude-oil"),
            ("Minério de Ferro", "https://br.investing.com/commodities/iron-ore-62-cfr-futures"),
            ("Ouro",             "https://br.investing.com/commodities/gold"),
            ("Aço",              "https://br.investing.com/commodities/us-steel-coil-futures?cid=1178216"),
        ], COLORS["red"])
    with g2:
        render_link_card("Bolsas & Análise", [
            ("Forecast Bolsas Mundiais",  "https://tradingeconomics.com/forecast/stock-market"),
            ("Bolsas Mundiais",           "https://tradingeconomics.com/shares"),
            ("Preço-alvo ações BR",       "https://analisa.genialinvestimentos.com.br/acoes/"),
            ("Sentimento Investidor EUA", "https://www.aaii.com/sentimentsurvey"),
            ("Agenda Semana Mundo",       "https://tradingeconomics.com/calendar"),
        ], COLORS["green"])
    with g3:
        render_link_card("Indicadores Macro", [
            ("Balança Comercial BR",    "https://tradingeconomics.com/brazil/balance-of-trade"),
            ("Dívida EUA",              "https://www.jec.senate.gov/public/vendor/_accounts/JEC-R/debt/Monthly%20Debt%20Update.html"),
            ("Incerteza EUA (FRED)",    "https://fred.stlouisfed.org/series/USEPUINDXM"),
            ("Dívida/PIB G20",          "https://tradingeconomics.com/country-list/government-debt-to-gdp?continent=g20"),
            ("Confiança Consumidor G20","https://tradingeconomics.com/country-list/consumer-confidence?continent=g20"),
            ("BCB Gráficos",            "https://www.bcb.gov.br/estatisticas"),
        ], COLORS["teal"])
    with g4:
        render_link_card("Ferramentas", [
            ("FinViz",      "https://finviz.com/"),
            ("TradingView", "https://br.tradingview.com/"),
        ], COLORS["sky"])

# ── Botão de atualização ──────────────────────────────────────────
st.markdown("---")
col1, col2, col3 = st.columns([3,1,3])
with col2:
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
