"""Interface Streamlit para pesquisa de decks Affinity e cotação exclusiva da loja."""
import csv
import io
import time
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from bot_magic import ARCHETYPE, HEADERS, fetch, listing_decks, load_catalog, parse_deck, quotes_for_card

st.set_page_config(page_title="Magic Deck Finder | Pauper Affinity", page_icon="🃏", layout="wide")
st.markdown("""<style>
.block-container{padding-top:2rem;max-width:1200px}
div[data-testid="stMetric"]{background:rgba(120,120,120,.08);border-radius:12px;padding:14px}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=3600, show_spinner=False)
def get_decks(arch_url, limit):
    session = requests.Session()
    session.headers.update(HEADERS)
    index = fetch(session, arch_url)
    links = listing_decks(index, max(25, limit * 4))
    if not links:
        raise ValueError("Nenhum link Affinity foi identificado. O MTGTop8 pode ter alterado a estrutura da página.")
    result = []
    problems = []
    for title, url in links:
        if len(result) >= limit:
            break
        time.sleep(1.25)
        try:
            main, side = parse_deck(fetch(session, url))
            if sum(main.values()) == 60 and sum(side.values()) == 15:
                result.append((title, url, dict(main), dict(side)))
            else:
                problems.append(f"Lista incompleta: {title} ({sum(main.values())}+{sum(side.values())}).")
        except (requests.RequestException, ValueError) as error:
            problems.append(f"Falha ao consultar {title}: {error}")
    return result, problems


def catalog_from_upload(upload):
    """Usa o mesmo validador de CSV do motor existente sem gravar upload permanentemente."""
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        dest = Path(temp) / "catalogo.csv"
        dest.write_bytes(upload.getvalue())
        return load_catalog(dest)


def evaluate(decks, catalog, include_side):
    summaries, cards = [], []
    for title, url, main, side in decks:
        need = Counter(main)
        if include_side:
            need.update(side)
        purchased_total = 0
        cost_total = Decimal("0")
        missing_total = 0
        for card in sorted(need):
            qty = need[card]
            found, missing, cost, offers = quotes_for_card(card, qty, catalog)
            purchased_total += found
            missing_total += missing
            cost_total += cost
            sections = ", ".join(z for z, items in (("Main", main), ("Sideboard", side)) if card in items)
            if offers:
                for count, offer in offers:
                    cards.append({"Deck": title, "Seção": sections, "Carta": card, "Necessárias": qty,
                                  "Encontradas": found, "Faltantes": missing, "Qtd. oferta": count,
                                  "Edição": offer["edicao"], "Preço unitário (R$)": float(offer["preco"]),
                                  "Subtotal (R$)": float(count * offer["preco"]), "Link da loja": offer["url"]})
            else:
                cards.append({"Deck": title, "Seção": sections, "Carta": card, "Necessárias": qty,
                              "Encontradas": 0, "Faltantes": qty, "Qtd. oferta": 0, "Edição": "",
                              "Preço unitário (R$)": None, "Subtotal (R$)": 0.0, "Link da loja": ""})
        summaries.append({"Deck": title, "Link MTGTop8": url, "Cartas disponíveis": purchased_total,
                          "Cartas faltantes": missing_total, "Custo encontrado (R$)": float(cost_total),
                          "Custo total (R$)": float(cost_total) if missing_total == 0 else None,
                          "Situação": "Completo" if missing_total == 0 else "Incompleto"})
    summaries.sort(key=lambda r: (r["Situação"] != "Completo", r["Custo encontrado (R$)"]))
    return pd.DataFrame(summaries), pd.DataFrame(cards)


def make_csv(df):
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")

st.title("🃏 Magic Deck Finder")
st.caption("MTGTop8 define **quais cartas procurar**. Somente o catálogo da Caverna do Basdão define **preços e estoque**.")
with st.sidebar:
    st.header("Configurações")
    st.selectbox("Formato", ["Pauper"], disabled=True)
    st.selectbox("Arquétipo", ["Affinity"], disabled=True)
    max_decks = st.number_input("Quantidade de decks", min_value=1, max_value=20, value=10, step=1)
    include_side = st.checkbox("Incluir sideboard", value=True)
    st.caption("Critério: decks completos pelo menor preço. Incompletos aparecem depois, com custo **parcial**.")
    arch_url = st.text_input("URL do arquétipo MTGTop8", value=ARCHETYPE)
    st.divider()
    st.subheader("Catálogo da loja")
    upload = st.file_uploader("Enviar catálogo CSV da Caverna do Basdão", type=["csv"])
    with open(Path(__file__).parent / "catalogo_loja_modelo.csv", "rb") as template:
        st.download_button("Baixar modelo do catálogo", template.read(), "catalogo_loja_modelo.csv", "text/csv")
    st.caption("Formato: nome;edicao;preco;estoque;url. Importação manual enquanto não existir integração autorizada com a loja.")

st.info("A loja não é consultada automaticamente: o acesso automatizado apresentou bloqueio 403. Para calcular preços reais, carregue o CSV do estoque da loja. O arquivo modelo é apenas ilustrativo.")
if st.button("🔎 Buscar 10 decks e comparar".replace("10", str(max_decks)), type="primary", use_container_width=True):
    if not upload:
        st.warning("Envie primeiro um catálogo CSV da loja. A busca de decklists pode ser testada separadamente abaixo.")
    else:
        try:
            catalog = catalog_from_upload(upload)
            with st.spinner("Consultando decklists e cruzando as cartas com o catálogo..."):
                decks, problems = get_decks(arch_url, max_decks)
                if not decks:
                    st.error("Nenhuma lista válida foi extraída do MTGTop8; não há valores a apresentar.")
                else:
                    summary, details = evaluate(decks, catalog, include_side)
                    st.session_state["analysis"] = (summary, details, problems)
        except Exception as err:
            st.error(f"Não foi possível concluir a pesquisa: {err}")

if st.button("📋 Consultar somente as listas do MTGTop8"):
    try:
        with st.spinner("Lendo listas públicas..."):
            decks, problems = get_decks(arch_url, max_decks)
        st.session_state["decks"] = (decks, problems)
    except Exception as err:
        st.error(f"Não foi possível consultar o MTGTop8: {err}")

if "decks" in st.session_state:
    decks, problems = st.session_state["decks"]
    st.subheader(f"Decklists encontradas: {len(decks)}")
    for name, url, main, side in decks:
        with st.expander(name):
            st.markdown(f"[Ver deck no MTGTop8]({url})")
            st.write("**Main deck**")
            st.dataframe(pd.DataFrame([{"Quantidade": q, "Carta": card} for card,q in main.items()]), hide_index=True)
            if include_side:
                st.write("**Sideboard**")
                st.dataframe(pd.DataFrame([{"Quantidade": q, "Carta": card} for card,q in side.items()]), hide_index=True)
    if problems:
        with st.expander(f"Avisos de extração ({len(problems)})"):
            st.write("\n".join(problems))

if "analysis" in st.session_state:
    summary, details, problems = st.session_state["analysis"]
    st.divider()
    st.subheader("Comparação de custo e disponibilidade")
    c1,c2,c3 = st.columns(3)
    c1.metric("Decks válidos", len(summary))
    c2.metric("Decks completos", int((summary["Situação"] == "Completo").sum()))
    c3.metric("Menor custo completo", f'R$ {summary["Custo total (R$)"].min():,.2f}' if summary["Custo total (R$)"].notna().any() else "Nenhum")
    st.caption("Custo encontrado em decks incompletos NÃO representa o custo total para montá-los. Cada deck é cotado separadamente; estoques não são reservados entre decks.")
    st.dataframe(summary, hide_index=True, use_container_width=True, column_config={"Link MTGTop8": st.column_config.LinkColumn("Lista original")})
    selection = st.selectbox("Detalhar cartas e ofertas do deck", summary["Deck"].tolist())
    subset = details[details["Deck"] == selection]
    tabs = st.tabs(["Todas as cartas", "Cartas faltantes"])
    with tabs[0]:
        st.dataframe(subset, use_container_width=True, hide_index=True, column_config={"Link da loja": st.column_config.LinkColumn("Comprar")})
    with tabs[1]:
        st.dataframe(subset[subset["Faltantes"] > 0], use_container_width=True, hide_index=True)
    a,b = st.columns(2)
    a.download_button("⬇️ Comparação dos decks (CSV)", make_csv(summary), "comparacao_decks.csv", "text/csv")
    b.download_button("⬇️ Cartas e ofertas (CSV)", make_csv(details), "cartas_e_ofertas.csv", "text/csv")
    if problems:
        with st.expander(f"Avisos ({len(problems)})"):
            st.write("\n".join(problems))

st.divider()
st.caption("Versão 1.1 • Pesquisa sujeita à disponibilidade pública e às regras do MTGTop8. Nenhum preço do MTGTop8 é utilizado.")
