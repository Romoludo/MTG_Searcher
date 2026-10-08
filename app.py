import io
from datetime import datetime
import pandas as pd
import streamlit as st
from lojas import collect_piedade, STORE_URL
from core import parse_deck, mtgtop8_deck, card_data, inventory_price, norm, similarity

st.set_page_config(page_title='MTG Londrina | Pauper', page_icon='🃏', layout='wide')
st.title('🃏 MTG Londrina — Pauper')
st.caption('Monte decks Pauper com orçamento e estoque de lojas físicas de Londrina/PR. Anúncios públicos podem ser coletados da Piedade; confirme preço e estoque diretamente na loja.')

if 'deck' not in st.session_state:
    st.session_state.deck = {'Principal': {}, 'Sideboard': {}}
if 'inventory' not in st.session_state:
    st.session_state.inventory = pd.DataFrame(columns=['loja', 'carta', 'quantidade', 'preco', 'url'])
if 'replacements' not in st.session_state:
    st.session_state.replacements = {}
if 'inventory_meta' not in st.session_state:
    st.session_state.inventory_meta = None

@st.cache_data(ttl=86400, show_spinner=False)
def cached_card(name):
    return card_data(name)

st.sidebar.header('Configurações')
budget = st.sidebar.number_input('Orçamento máximo (R$)', min_value=0.0, value=250.0, step=10.0)
with_side = st.sidebar.checkbox('Incluir sideboard no orçamento', value=True)
st.sidebar.info('Versão inicial: Pauper, compra exclusivamente em lojas locais cadastradas. Nenhum estoque é presumido.')

tab1, tab2, tab3 = st.tabs(['1 · Importar deck', '2 · Estoque local', '3 · Otimizar'])
with tab1:
    st.subheader('Importar deck Pauper')
    url = st.text_input('Link do deck MTGTop8 (opcional)', placeholder='https://www.mtgtop8.com/event?e=...&d=...')
    if st.button('Tentar importar do MTGTop8'):
        if not url.strip():
            st.warning('Cole um link primeiro.')
        else:
            try:
                m, s = mtgtop8_deck(url.strip())
                st.session_state.deck = {'Principal': dict(m), 'Sideboard': dict(s)}
                st.session_state.replacements = {}
                st.success('Lista importada. Confira as quantidades abaixo.')
            except Exception as e:
                st.error(f'Importação indisponível: {e}')
    sample = '4 Myr Enforcer\n4 Frogmite\n4 Thoughtcast\n\nSideboard\n2 Hydroblast'
    raw = st.text_area('Ou cole a lista (recomendado para páginas que bloqueiam extração)', height=220,
                       placeholder=sample)
    if st.button('Carregar lista colada'):
        m, s = parse_deck(raw)
        if not m:
            st.error('Não identifiquei cartas. Use linhas como: 4 Myr Enforcer')
        else:
            st.session_state.deck = {'Principal': dict(m), 'Sideboard': dict(s)}
            st.session_state.replacements = {}
            st.success('Lista carregada.')
    deck = st.session_state.deck
    st.metric('Cartas no principal', sum(deck['Principal'].values()))
    st.metric('Cartas no sideboard', sum(deck['Sideboard'].values()))
    if deck['Principal']:
        st.dataframe(pd.DataFrame([{'seção': k, 'quantidade': q, 'carta': n}
                                   for k, v in deck.items() for n, q in v.items()]), hide_index=True)
        if sum(deck['Principal'].values()) != 60:
            st.warning('O deck principal Pauper construído normalmente exige pelo menos 60 cartas; confira a lista.')
        if sum(deck['Sideboard'].values()) > 15:
            st.warning('Sideboard com mais de 15 cartas.')

with tab2:
    st.subheader('Preços de cartas em lojas físicas de Londrina')
    st.write('Atualize anúncios públicos da loja piloto ou importe um CSV. Valores publicados **não são confirmação de estoque físico**. Consulte a loja antes de comprar.')
    st.markdown(f'**Loja piloto:** [Piedade Card House — catálogo público]({STORE_URL}). Apenas anúncios encontrados nas páginas consultadas entram na planilha.')
    pages = st.number_input('Páginas públicas para verificar (máximo 5)', min_value=1, max_value=5, value=2, step=1)
    if st.button('🔄 Atualizar preços da Piedade', type='primary'):
        with st.spinner('Consultando páginas públicas sem contornar bloqueios...'):
            try:
                collected, meta = collect_piedade(max_pages=pages)
                if collected:
                    imported = pd.DataFrame(collected)
                    current = st.session_state.inventory.copy()
                    # Replace only the pilot store; preserve manually entered offers from other stores.
                    current = current[current['loja'].astype(str).str.casefold() != 'piedade card house']
                    st.session_state.inventory = pd.concat([current, imported], ignore_index=True)
                    st.session_state.inventory_meta = meta
                    st.success(f"{len(collected)} anúncios identificados nas páginas consultadas. Inventário PARCIAL.")
                    st.rerun()
                else:
                    st.warning('Nenhum anúncio foi extraído com segurança. O site pode ter alterado a estrutura ou carregar produtos por JavaScript. O estoque anterior foi preservado.')
            except Exception as exc:
                st.error(f'Coleta indisponível: {exc}. Importe o CSV ou registre ofertas manualmente.')
    if st.session_state.inventory_meta:
        meta = st.session_state.inventory_meta
        st.warning(meta['aviso'])
        st.caption(f"Última consulta: {meta['consultado_em_utc']} | Anúncios identificados: {meta['anuncios_lidos']}")
        with st.expander('Detalhes da coleta'):
            st.json(meta['paginas'])

    st.download_button('Baixar modelo CSV', 'loja,carta,quantidade,preco,url\n', 'modelo_estoque.csv', 'text/csv')
    upload = st.file_uploader('Importar CSV', type=['csv'])
    if upload is not None and st.button('Usar CSV enviado'):
        try:
            data = pd.read_csv(upload, sep=None, engine='python')
            required = {'loja', 'carta', 'quantidade', 'preco', 'url'}
            if not required.issubset(data.columns):
                st.error(f'Colunas obrigatórias: {sorted(required)}')
            else:
                st.session_state.inventory = data[['loja', 'carta', 'quantidade', 'preco', 'url']].copy()
                st.session_state.inventory_meta = None
                st.success('Ofertas importadas.')
        except Exception as e:
            st.error(f'Erro no CSV: {e}')
    edited = st.data_editor(st.session_state.inventory, num_rows='dynamic', hide_index=True,
                            column_config={'preco': st.column_config.NumberColumn('preco', min_value=0, format='R$ %.2f'),
                                           'quantidade': st.column_config.NumberColumn('quantidade', min_value=0, step=1)},
                            key='inventory_editor')
    if st.button('Salvar ofertas nesta sessão'):
        st.session_state.inventory = edited.copy()
        st.session_state.inventory_meta = None
        st.success('Ofertas salvas para esta sessão. Exporte-as para não perder os dados.')
    st.download_button('Exportar ofertas atuais', edited.to_csv(index=False).encode('utf-8-sig'), 'estoque_londrina.csv', 'text/csv')

with tab3:
    original = st.session_state.deck
    if not original['Principal']:
        st.info('Importe um deck primeiro.')
    else:
        active = {'Principal': {}, 'Sideboard': {}}
        for section, cards in original.items():
            for card, quantity in cards.items():
                changed = st.session_state.replacements.get((section, card), card)
                active[section][changed] = active[section].get(changed, 0) + quantity
        effective = active if with_side else {'Principal': active['Principal']}
        try:
            df = st.session_state.inventory.copy()
            df['preco'] = pd.to_numeric(df['preco'], errors='coerce')
            df['quantidade'] = pd.to_numeric(df['quantidade'], errors='coerce')
            df = df.dropna(subset=['loja', 'carta', 'preco', 'quantidade'])
            df = df[(df['preco'] >= 0) & (df['quantidade'] >= 0)]
            df['quantidade'] = df['quantidade'].astype(int)
            offers = df.to_dict('records')
        except Exception as e:
            st.error(f'Dados inválidos no estoque: {e}')
            offers = []
        buys, missing = inventory_price(offers, effective)
        subtotal = sum(x['total'] for x in buys)
        complete = not missing
        a, b, c = st.columns(3)
        a.metric('Custo de cartas encontradas', f'R$ {subtotal:,.2f}')
        b.metric('Limite', f'R$ {budget:,.2f}')
        c.metric('Cópias sem oferta', sum(x['quantidade'] for x in missing))
        if not complete:
            st.warning('Preço total do deck desconhecido: há cartas sem oferta local. O valor exibido é apenas parcial.')
        elif subtotal <= budget:
            st.success('Deck encontrado integralmente dentro do orçamento!')
        else:
            st.error(f'Deck completo excede o teto em R$ {subtotal-budget:,.2f}.')
        if buys:
            st.subheader('Lista de compras')
            st.dataframe(pd.DataFrame(buys), hide_index=True, use_container_width=True)
            st.download_button('Baixar compras CSV', pd.DataFrame(buys).to_csv(index=False).encode('utf-8-sig'), 'compras.csv', 'text/csv')
        if missing:
            st.subheader('Cartas faltantes')
            st.dataframe(pd.DataFrame(missing), hide_index=True)
        st.subheader('Substituições sugeridas (disponibilidade + similaridade)')
        st.caption('Alternativas são estimativas heurísticas, não equivalências garantidas. Verifique efeitos, regras, sinergias e legalidade antes de comprar.')
        if st.button('Buscar alternativas para cartas ausentes ou caras'):
            st.session_state['show_suggestions'] = True
        if st.session_state.get('show_suggestions'):
            available = sorted(set(str(x['carta']) for x in offers if x['quantidade'] > 0))
            target_names = set(x['carta'] for x in missing)
            for x in buys:
                if x['preco_unitario'] >= 5:
                    target_names.add(x['carta'])
            if not target_names:
                st.info('Não há cartas faltantes ou com preço unitário igual ou superior a R$ 5.')
            for section, cards in active.items():
                if section == 'Sideboard' and not with_side:
                    continue
                for name in cards:
                    if name not in target_names:
                        continue
                    try:
                        base = cached_card(name)
                        possibilities = []
                        for candidate in available[:30]:
                            try:
                                info = cached_card(candidate)
                                score = similarity(base, info)
                                eligible = [x for x in offers if norm(x['carta']) == norm(candidate)]
                                capacity = sum(x['quantidade'] for x in eligible)
                                if score >= 0 and capacity >= cards[name]:
                                    possibilities.append((score, min(x['preco'] for x in eligible), candidate))
                            except Exception:
                                continue
                        possibilities.sort(key=lambda x: (-x[0], x[1]))
                        with st.expander(f'{name} — {cards[name]} cópias', expanded=False):
                            if base['pauper'] != 'legal':
                                st.warning('A carta original não aparece como legal em Pauper no Scryfall.')
                            if possibilities:
                                options = [name] + [x[2] for x in possibilities[:8]]
                                choice = st.selectbox('Trocar por', options, key=f'{section}-{name}')
                                for score, price, candidate in possibilities[:8]:
                                    st.write(f'{candidate} — similaridade {score:.0%}, menor preço R$ {price:.2f}')
                                if st.button('Aplicar troca', key=f'apply-{section}-{name}'):
                                    st.session_state.replacements[(section, name)] = choice
                                    st.rerun()
                            else:
                                st.write('Nenhuma alternativa local encontrada na amostra disponível.')
                    except Exception as e:
                        st.caption(f'Não foi possível verificar {name}: {e}')
        if st.session_state.replacements:
            if st.button('Desfazer todas as trocas'):
                st.session_state.replacements = {}
                st.rerun()
        fulltext = '\n'.join(f'{q} {n}' for n, q in active['Principal'].items()) + '\n\nSideboard\n' + '\n'.join(f'{q} {n}' for n, q in active['Sideboard'].items())
        st.download_button('Exportar deck atualizado TXT', fulltext, 'pauper_otimizado.txt', 'text/plain')
