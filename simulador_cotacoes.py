# simulador_cotacoes.py — Pesquisa -> Orçamento (qtd/discount OU preço direto) + Google por item
# Rodar: streamlit run simulador_cotacoes.py

import os, io, re, unicodedata, time, base64
from typing import List, Dict, Tuple
import pandas as pd
import requests
import streamlit as st

# =================== CHAVES E DEPENDÊNCIAS ===================
SERPAPI_KEY = os.getenv("SERPAPI_API_KEY", "")
try:
    from dotenv import load_dotenv
    load_dotenv()
    SERPAPI_KEY = os.getenv("SERPAPI_API_KEY", "") or SERPAPI_KEY
except Exception:
    pass

from fuzzywuzzy import fuzz
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from xml.sax.saxutils import escape

# =================== UI BASE ===================
st.set_page_config(page_title="Simulador de Cotações - Made in Natural", layout="wide")

FONT_SCALE = 0.92
st.markdown(f"""
<style>
html, body, [data-testid="stAppViewContainer"] * {{ font-size: {FONT_SCALE}rem; }}
h1 {{ font-size: 1.45rem !important; margin: 0 !important; }}
h2 {{ font-size: 1.2rem !important; }}
h3 {{ font-size: 1.05rem !important; }}
[data-testid="stMetricValue"] {{ font-size: 1.2rem !important; }}
</style>
""", unsafe_allow_html=True)

BASE_FILE = "tab_precos.xlsx"

# ====== LOGO ======
LOGO_EMBED_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAOEAAADhCAMAAAAJbSJIAAABI1BMVEX////k6FPzQCNGiC5DhikxfgpA"
"ZrT3/f+Jm1/q9f2VsnWnq6+3yc7T3v/7x+fPp8uZ6q7rT39/m9PjW4eXW3+F3rL2Pr8PZ5OeDrsHc6fK1"
"x9zJ2uBppcC7zdnS4N6An8CSoM6Xn8u0yuDY4+fA0t6Tn8x6pb+xyt0/d7tEgKZ6qL3T2d1whbZ0m8bS2"
"N7o8vGRoM+SuNFXlcN2r794sbm9zt6xyt97q8C6zth+scB1qLk2o7WYs9OqvNqWtdNpmcCkp8u1yuB3rL"
"0xobK9zN+8zN7C1d5+jr+3zd6Tnsxkh7a1yN+zu9+HpcCwxts9p7y4zdysv9v////0tY6NAAAAYHRSTlMA"
"AQIDBAYICQoLDA8RExUYGhweISMkKC0xNjk7QEVHSUpOUFZbX2FmaGxvdXuCh5CXmJ2goaKmp6irrrG0t7"
"m6v8CExcbK0Nna3OPq7PH0+/z+Ai2eAAABUklEQVR4nO3dS47cQBiG0b2z0yYy3Q0lq9a1gEwIRV28//+F"
"y5lO0d0gq6n3w8XH5O2gq2xkqC8p9H0h0eR9XWcY7J8kq5mJ7b2Xq9WJf7r7e2W0zqJ7o7f3uWm3mM3k4D"
"rDRU7o8y8V6W0k2G3b2n3GSVgqH0Ywq7w1w0y8h7C4V9VY9E6cR8n0p6K7QW+H0n9iK1l9m9Dq9l3ZcY2b"
"2Kz0Q2n4kQfZyVnKq7oN8Tg9zM9Qz7WZb2sC7b4p2Y0s2l8bF7cV0Q7f2xQb7mG5k6k2w1o3b5lq8sH6M2"
"l1j5q1v6p3lK8QJg2w2m4HkM2l3j6q2x5r4t9Q2l2r7o5k8o3c7v1n5o3EJj9v2r5j6M2mAAAAAElFTkSuQmCC")

def default_logo_bytes() -> bytes:
    try:
        return base64.b64decode(LOGO_EMBED_B64)
    except Exception:
        return b""

def load_logo_bytes():
    if "logo_bytes" in st.session_state and st.session_state["logo_bytes"]:
        return st.session_state["logo_bytes"]
    for name in ("Logo.png", "logo.png", "logo.jpg", "logo.jpeg"):
        if os.path.exists(name):
            try:
                from PIL import Image as PILImage
                with PILImage.open(name) as im:
                    buf = io.BytesIO(); im.save(buf, format="PNG")
                    st.session_state["logo_bytes"] = buf.getvalue()
                    return st.session_state["logo_bytes"]
            except Exception:
                pass
    st.session_state["logo_bytes"] = default_logo_bytes()
    return st.session_state["logo_bytes"]

logo_bytes = load_logo_bytes()
if logo_bytes:
    b64 = base64.b64encode(logo_bytes).decode()
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;margin:0 0 8px 0;">
          <img src="data:image/png;base64,{b64}" style="height:56px"/>
          <div style="font-size:1.35rem;font-weight:700;">Simulador de Cotações - Made in Natural</div>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.header("Simulador de Cotações - Made in Natural")

st.markdown("---")

# =================== HELPERS ===================
def _norm(s: str) -> str:
    s = str(s).strip().lower().replace("\u00A0"," ")
    s = ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

def fmt_brl(v: float) -> str:
    try:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {v}"

def to_float_brl(txt: str):
    if txt is None: return None
    s = str(txt).replace("R$","").replace(".","").replace(",",".")
    m = re.search(r"(-?\d+(\.\d+)?)", s)
    return float(m.group(1)) if m else None

def to_float_pct(v) -> float:
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace("%","").replace(" ","").replace(",",".")
    try:
        return float(s) if s else 0.0
    except Exception:
        return 0.0

def fmt_pct_br(x: float) -> str:
    return f"{float(x):.2f}%".replace(".", ",")

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def parse_pct_text(s: str) -> float:
    # Aceita '0,5', '0.5', ' 10 % ', '-7,25', 'desc 5,5%'
    if s is None:
        return 0.0
    s = str(s).strip().replace('%','').replace(' ','').replace(',', '.')
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0

def parse_money_text(s: str) -> float:
    # Aceita '12,34', '12.34', 'R$ 1.234,56', '1.234,56'
    if s is None:
        return 0.0
    s = str(s).strip().replace("R$","").replace(" ","")
    s = s.replace(".", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    v = float(m.group(1)) if m else 0.0
    return max(0.0, v)

# =================== ENTRADAS QUE SEMPRE PERMITEM DIGITAR ===================
def pct_input_text(label: str, key: str, container) -> float:
    """Campo de % baseado em text_input (aceita vírgula/ponto). Sem botões."""
    if key not in st.session_state:
        st.session_state[key] = 0.0
    shown = f"{st.session_state[key]:.2f}".replace('.', ',')
    raw = container.text_input(label, value=shown, key=f"txt_{key}")
    v = clamp(parse_pct_text(raw), -100.0, 100.0)
    st.session_state[key] = v
    return v


def money_input_text(label: str, key: str, container):
    """Campo de preço baseado em text_input (aceita vírgula/ponto)."""
    if key not in st.session_state:
        st.session_state[key] = 0.0
    raw = container.text_input(label, value=f"{st.session_state[key]:.2f}".replace('.', ','), key=f"txt_{key}")
    v = parse_money_text(raw)
    st.session_state[key] = v
    return v

# =================== PLANILHA ===================
@st.cache_data(show_spinner=False)
def ler_planilha_robusta(path: str) -> pd.DataFrame:
    all_sheets = pd.read_excel(path, sheet_name=None)
    best, best_score = None, -1
    for _, df in all_sheets.items():
        cols = [_norm(c) for c in df.columns]
        score = sum(k in cols for k in [
            "produto","codigo","código","categoria","subcategoria","preco","preço","sku","descricao","descrição"
        ])
        if score > best_score:
            best, best_score = df.copy(), score
    if best is None:
        raise ValueError("Não foi possível identificar uma planilha válida.")
    ALIAS = {
        "produto":"Produto","nome do produto":"Produto","descricao":"Produto","descrição":"Produto",
        "codigo":"Código","código":"Código","cod":"Código","sku":"Código",
        "categoria":"Categoria",
        "subcategoria":"Subcategoria","sub-categoria":"Subcategoria","sub categoria":"Subcategoria",
        "preco":"Preço","preço":"Preço","preco de tabela":"Preço","preco tabela":"Preço"
    }
    ren = {}
    for c in best.columns:
        k = _norm(c)
        if k in ALIAS: ren[c] = ALIAS[k]
    best.rename(columns=ren, inplace=True)
    campos = {"Produto","Código","Categoria","Subcategoria","Preço"}
    faltando = campos - set(best.columns)
    if faltando:
        raise ValueError(f"Faltando colunas: {sorted(faltando)}")
    best["Preço"] = best["Preço"].apply(lambda x: float(x) if pd.notnull(x) else 0.0)
    for col in ["Produto","Código","Categoria","Subcategoria"]:
        best[col] = best[col].astype(str)
    best["__norm"] = best["Produto"].map(_norm)
    return best

# =================== GOOGLE SHOPPING ===================
@st.cache_data(show_spinner=False, ttl=60*30)
def consultar_google_shopping(query: str, num=6, location="São Paulo, State of São Paulo, Brazil") -> List[Dict]:
    if not SERPAPI_KEY: return []
    params = {"engine":"google_shopping","q":query,"location":location,"hl":"pt-BR","gl":"br","api_key":SERPAPI_KEY,"num":num}
    try:
        r = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
        if r.status_code != 200: return []
        data = r.json()
        out = []
        for p in data.get("shopping_results", []) or []:
            title, source, link = p.get("title"), p.get("source"), p.get("link")
            price = p.get("extracted_price")
            if price is None: price = to_float_brl(p.get("price"))
            if title and price:
                out.append({"Título":title, "Loja":source, "Preço Mercado (R$)":float(price), "Link":link})
        return out
    except Exception:
        return []

def melhores_sugestoes(df: pd.DataFrame, query: str, limite=12, thr=45):
    qn = _norm(query)
    if not qn: return []
    scores: List[Tuple[int,int]] = []
    for idx, row in df.iterrows():
        s = fuzz.token_set_ratio(qn, row["__norm"])
        if s >= thr:
            scores.append((s, idx))
    scores.sort(reverse=True)
    return [(df.loc[i], s) for s, i in scores[:limite]]

# =================== CARREGAR BASE ===================
try:
    df = ler_planilha_robusta(BASE_FILE)
except Exception as e:
    st.error(f"Erro ao abrir '{BASE_FILE}': {e}")
    st.stop()

# =================== ESTADO GLOBAL ===================
if "itens" not in st.session_state:
    st.session_state["itens"] = []

# =================== TELAS ===================
def ui_pesquisa(df: pd.DataFrame):
    st.subheader("🔎 Pesquisar produto (selecione para adicionar)")
    if "consulta" not in st.session_state:
        st.session_state["consulta"] = ""
    if st.session_state.get("reset_consulta", False):
        st.session_state["consulta"] = ""
        st.session_state["reset_consulta"] = False

    consulta = st.text_input("Digite parte do nome (ex.: coca-cola, granola 800g)", key="consulta")

    if consulta.strip():
        sugestoes = melhores_sugestoes(df, consulta.strip(), limite=10, thr=45)
        if not sugestoes:
            st.warning("Nenhuma sugestão encontrada.")
        else:
            with st.form("pesquisa_form", clear_on_submit=True):
                st.caption("Marque os itens que deseja adicionar e informe as quantidades.")
                selecionados = []
                for idx, (row, score) in enumerate(sugestoes, start=1):
                    c0, c1, c2, c3, c4 = st.columns([0.6, 5, 1.8, 1.2, 1.6])
                    sel_key = f"sel_{idx}"
                    qty_key = f"qty_{idx}"
                    with c0:
                        sel = st.checkbox("", key=sel_key, value=False)
                    with c1:
                        st.markdown(
                            f"**{row['Produto']}**  \n"
                            f"Código: `{row['Código']}` • Categoria: {row['Categoria']} • Sub: {row['Subcategoria']}"
                        )
                    with c2:
                        st.markdown(f"**{fmt_brl(float(row['Preço']))}**")
                    with c3:
                        st.caption(f"Match: {score}%")
                    with c4:
                        qtd = st.number_input("Qtd", min_value=1, step=1, value=1, key=qty_key)
                    if sel:
                        selecionados.append({
                            "Código": str(row["Código"]),
                            "Produto": str(row["Produto"]),
                            "Categoria": str(row["Categoria"]),
                            "Subcategoria": str(row["Subcategoria"]),
                            "Preço Tabela": float(row["Preço"]),
                            "Quantidade": int(qtd),
                        })
                submitted = st.form_submit_button("➕ Adicionar selecionados")

            if submitted and selecionados:
                for sel in selecionados:
                    codigo  = str(sel["Código"])
                    produto = str(sel["Produto"])
                    preco_tab = float(sel["Preço Tabela"])
                    qtd = int(sel["Quantidade"])
                    existente = next(
                        (it for it in st.session_state["itens"]
                         if str(it["Código"]) == codigo and _norm(it["Produto"]) == _norm(produto)),
                        None
                    )
                    if existente:
                        preco_final = float(existente.get("Preço Negociado", preco_tab) or preco_tab)
                        existente["Quantidade"] = int(existente.get("Quantidade", 1)) + qtd
                        existente["Total"] = round(preco_final * int(existente["Quantidade"]), 2)
                    else:
                        preco_final = preco_tab
                        st.session_state["itens"].append({
                            "Produto": produto,
                            "Código": codigo,
                            "Categoria": sel["Categoria"],
                            "Subcategoria": sel["Subcategoria"],
                            "Preço Tabela": preco_tab,
                            "Desconto %": 0.0,
                            "Quantidade": qtd,
                            "Preço Direto": 0.0,
                            "Preço Negociado": preco_final,
                            "Total": round(preco_final * qtd, 2),
                            "Mercado": []
                        })
                st.success(f"{len(selecionados)} item(ns) adicionados ao orçamento.")
                st.session_state["reset_consulta"] = True
                st.rerun()

def ui_item_avulso():
    st.subheader("➕ Item avulso (não está na tabela)")
    with st.form("form_item_avulso", clear_on_submit=True):
        nome = st.text_input("Descrição do produto *", key="avulso_nome", placeholder="Ex.: Granola Zero Açúcar 1kg")
        c1, c2, c3 = st.columns([2, 1, 1])
        preco_raw = c1.text_input("Preço (R$) *", key="avulso_preco_txt", value="0,00")
        qtd   = c2.number_input("Quantidade *", min_value=1, step=1, value=1, key="avulso_qtd")
        codigo_opt = c3.text_input("Código (opcional)", key="avulso_cod", placeholder="Ex.: SKU-123")
        c4, c5 = st.columns([1, 1])
        categoria_opt    = c4.text_input("Categoria (opcional)", key="avulso_cat", placeholder="Avulso")
        subcategoria_opt = c5.text_input("Subcategoria (opcional)", key="avulso_subcat", placeholder="-")
        submitted_avulso = st.form_submit_button("➕ Incluir no orçamento")

    if submitted_avulso:
        nome_ok = (nome or "").strip()
        preco = parse_money_text(preco_raw)
        if not nome_ok or preco <= 0.0 or int(qtd) < 1:
            st.warning("Preencha **Descrição**, **Preço** (> 0) e **Quantidade** (≥ 1).")
        else:
            gen_code = f"AVULSO-{int(time.time()*1000) % 1000000}"
            codigo = (codigo_opt or "").strip() or gen_code
            categoria = (categoria_opt or "").strip() or "Avulso"
            subcat    = (subcategoria_opt or "").strip() or "-"
            preco_tab = float(preco)
            existente = next(
                (it for it in st.session_state["itens"]
                 if str(it["Código"]) == str(codigo) and _norm(it["Produto"]) == _norm(nome_ok)),
                None
            )
            if existente:
                preco_final = float(existente.get("Preço Negociado", preco_tab) or preco_tab)
                existente["Quantidade"] = int(existente.get("Quantidade", 1)) + int(qtd)
                existente["Total"] = round(preco_final * int(existente["Quantidade"]), 2)
                st.success(f"Quantidade atualizada: {nome_ok} (Qtd {existente['Quantidade']}).")
            else:
                preco_final = preco_tab
                st.session_state["itens"].append({
                    "Produto": nome_ok,
                    "Código": str(codigo),
                    "Categoria": categoria,
                    "Subcategoria": subcat,
                    "Preço Tabela": preco_tab,
                    "Desconto %": 0.0,
                    "Quantidade": int(qtd),
                    "Preço Direto": 0.0,
                    "Preço Negociado": preco_final,
                    "Total": round(preco_final * int(qtd), 2),
                    "Mercado": [],
                    "Avulso": True,
                })
                st.success(f"Item avulso adicionado: {nome_ok} (Qtd {int(qtd)}).")
            st.rerun()

def ui_orcamento(logo_bytes: bytes):
    st.subheader("🧾 Orçamento — informe Quantidade e Desconto (%) ou Preço direto")

    itens = st.session_state.get("itens", [])
    if not itens:
        st.info("Nenhum item selecionado. Use a aba **Pesquisar** ou **Item avulso** para adicionar produtos.")
        return

    total_geral = 0.0

    for idx, item in enumerate(itens):
        is_avulso = item.get("Avulso", False)
        badge = " <span style='background:#f59e0b;color:#111;padding:2px 6px;border-radius:10px;font-size:0.75rem;margin-left:6px;'>AVULSO</span>" if is_avulso else ""
        st.markdown(
            f"**{idx+1}. {item['Produto']}**{badge} "
            f"<span style='color:#6b7280'>[{item['Código']}]</span>",
            unsafe_allow_html=True
        )

        colA, colB, colC, colD, colE, colF, colG = st.columns([2,2,2,1,1,1,1])

        q_key = f"q_{idx}"
        d_key = f"d_{idx}"
        p_key = f"p_{idx}"

        # inicializa uma única vez
        if q_key not in st.session_state:
            st.session_state[q_key] = int(item.get("Quantidade", 1))
        if d_key not in st.session_state:
            st.session_state[d_key] = float(item.get("Desconto %", 0.0))
        if p_key not in st.session_state:
            st.session_state[p_key] = float(item.get("Preço Direto", 0.0))

        # Quantidade (inteiro OK com number_input)
        new_q = colA.number_input("Quantidade", min_value=1, step=1, key=q_key)

        # Preço direto (TEXT INPUT para não travar vírgula/ponto)
        new_p = money_input_text("Preço direto (opcional)", key=p_key, container=colC)

        # Limpar preço direto
        if colG.button("↩︎", key=f"clr_{idx}", help="Limpar preço direto"):
            st.session_state[p_key] = 0.0
            new_p = 0.0

        preco_tab = float(item["Preço Tabela"])

        if new_p and float(new_p) > 0.0:
            # quando há preço direto, desconto vira somente exibição
            desconto_calc = round((1 - (float(new_p) / preco_tab)) * 100.0, 2)
            colB.text_input("Desconto (%)", value=f"{desconto_calc:.2f}".replace('.', ','), key=f"view_{d_key}", disabled=True)
            preco_final = round(float(new_p), 2)
            desconto_usado = desconto_calc
            item["Preço Direto"] = preco_final
        else:
            # Desconto (%) como TEXT INPUT (aceita vírgula/ponto) + +/- botões
            new_d = pct_input_text("Desconto (%)", key=d_key, container=colB)
            colB.caption("Negativo = acréscimo (ex.: -10%).")
            preco_final = round(preco_tab * (1 - float(new_d)/100.0), 2)
            desconto_usado = float(new_d)
            item["Preço Direto"] = 0.0

        total = round(preco_final * int(new_q), 2)

        # atualiza item
        item["Quantidade"] = int(new_q)
        item["Desconto %"] = float(desconto_usado)
        item["Preço Negociado"] = preco_final
        item["Total"] = total

        colD.metric("Preço final", fmt_brl(preco_final))
        colE.metric("Total", fmt_brl(total))

        cF1, cF2 = colF.columns(2)
        ac_g = cF1.button("🔎", key=f"g_{idx}", help="Consultar Google Shopping p/ este produto")
        rem  = cF2.button("🗑️", key=f"rm_{idx}", help="Remover este item")

        if ac_g:
            resultados = consultar_google_shopping(item["Produto"])
            item["Mercado"] = resultados
            st.success("Consulta de mercado concluída!")

        if rem:
            st.session_state["itens"].pop(idx)
            st.success("Item removido.")
            st.rerun()
            return

        if item.get("Mercado"):
            with st.expander("Comparação de Preços (Google Shopping)"):
                st.dataframe(pd.DataFrame(item["Mercado"]), use_container_width=True)

        st.markdown("---")
        total_geral += total

    c1, c2 = st.columns([3,1])
    c1.subheader(" ")
    c2.metric("✅ Total geral", fmt_brl(total_geral))

    if st.button("🧹 Limpar orçamento", key="clear_cart"):
        st.session_state["itens"] = []
        for k in list(st.session_state.keys()):
            if k.startswith(("q_", "d_", "p_", "view_")):
                del st.session_state[k]
        st.session_state.pop("pdf_bytes", None)
        st.session_state.pop("pdf_name", None)
        st.success("Orçamento limpo.")
        st.rerun()
        return

# =================== NAV LATERAL ===================
with st.sidebar:
    st.header("Menu")
    view = st.radio("Ir para:", ["Pesquisar", "Item avulso", "Orçamento"], index=0)
    st.divider()
    itens = st.session_state.get("itens", [])
    subtotal = sum(float(i.get("Total", 0.0)) for i in itens)
    st.metric("💰 Parcial do orçamento", fmt_brl(subtotal))
    st.write(f"🛒 Itens no orçamento: **{len(itens)}**")

# =================== RENDER ===================
if view == "Pesquisar":
    ui_pesquisa(df)
elif view == "Item avulso":
    ui_item_avulso()
elif view == "Orçamento":
    ui_orcamento(logo_bytes)

# =================== PDF ===================
st.subheader("📤 Exportar PDF")
cliente = st.text_input("Cliente/Projeto (opcional):", "")
obs = st.text_area("Observações (opcional):", "")

def gerar_pdf_bytes(cliente: str, obs: str, itens: list, logo_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=30, bottomMargin=24)
    styles = getSampleStyleSheet()
    title_style = styles["Title"]; title_style.fontSize = 18
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=11)
    body_center = ParagraphStyle("body_center", parent=body, alignment=1)
    body_right  = ParagraphStyle("body_right",  parent=body, alignment=2)

    elems = []
    if logo_bytes:
        try:
            elems.append(RLImage(io.BytesIO(logo_bytes), width=3.5*cm, height=3.5*cm))
            elems.append(Spacer(1, 6))
        except Exception:
            pass

    title = "Orçamento - Made in Natural"
    if cliente.strip(): title += f" — {cliente.strip()}"
    elems.append(Paragraph(title, title_style))
    elems.append(Paragraph(time.strftime("Data: %d/%m/%Y %H:%M"), styles["Normal"]))
    if obs.strip():
        elems.append(Spacer(1, 6))
        elems.append(Paragraph(f"<b>Observações:</b> {escape(obs.strip())}", styles["Normal"]))
    elems.append(Spacer(1, 10))

    cab = ["Produto", "Qtd", "Preço Tabela", "Desc (%)", "Preço Final", "Total"]
    rows = []
    for i in itens:
        rows.append([
            Paragraph(escape(str(i["Produto"])), body),
            Paragraph(str(i["Quantidade"]), body_center),
            Paragraph(fmt_brl(float(i["Preço Tabela"])), body_right),
            Paragraph(fmt_pct_br(to_float_pct(i.get("Desconto %", 0))), body_center),
            Paragraph(fmt_brl(float(i["Preço Negociado"])), body_right),
            Paragraph(fmt_brl(float(i["Total"])), body_right),
        ])
    total_geral = sum(float(i["Total"]) for i in itens)
    rows.append(["", "", "", "", Paragraph("<b>TOTAL</b>", body_right), Paragraph(fmt_brl(total_geral), body_right)])

    col_widths = [260, 35, 75, 55, 70, 52]
    t = Table([cab] + rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME",  (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",  (0,0), (-1,0), 10),
        ("GRID",      (0,0), (-1,-1), 0.4, colors.black),
        ("VALIGN",    (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",     (1,1), (1,-2), "CENTER"),
        ("ALIGN",     (2,1), (2,-2), "RIGHT"),
        ("ALIGN",     (3,1), (3,-2), "CENTER"),
        ("ALIGN",     (4,1), (5,-2), "RIGHT"),
        ("TOPPADDING",(0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ]))
    elems.append(t)

    doc.build(elems)
    return buf.getvalue()

if st.button("📄 Gerar PDF"):
    with st.spinner("Gerando PDF..."):
        try:
            pdf_bytes = gerar_pdf_bytes(cliente, obs, st.session_state["itens"], logo_bytes)
            st.session_state["pdf_bytes"] = pdf_bytes
            st.session_state["pdf_name"] = "orcamento.pdf"
            st.success("PDF gerado! Use o botão abaixo para baixar.")
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")

if st.session_state.get("pdf_bytes"):
    st.download_button(
        "📥 Baixar PDF",
        data=st.session_state["pdf_bytes"],
        file_name=st.session_state.get("pdf_name", "orcamento.pdf"),
        mime="application/pdf"
    )
