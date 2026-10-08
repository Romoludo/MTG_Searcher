#!/usr/bin/env python3
"""MTGTop8 decklists -> comparação EXCLUSIVAMENTE com catálogo da loja.
Instalar: pip install requests beautifulsoup4
Executar: python bot_magic.py --catalogo catalogo_loja.csv
"""
import argparse
import csv
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.mtgtop8.com/'
ARCHETYPE = 'https://www.mtgtop8.com/archetype?a=512&f=PAU&meta=299'
HEADERS = {'User-Agent': 'DeckResearchBot/1.0 (personal deck research; respectful rate limits)'}
SECTIONS = {'LANDS', 'CREATURES', 'INSTANTS and SORC.', 'OTHER SPELLS', 'SIDEBOARD'}
CARD = re.compile(r'^\s*(\d{1,2})\s+(.+?)\s*$')


def fetch(session, url):
    response = session.get(url, timeout=25)
    response.raise_for_status()
    return BeautifulSoup(response.text, 'html.parser')


def normalize(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


def listing_decks(soup, limit):
    """Encontra links para decks na página Affinity; mantém ordem do site."""
    found, seen = [], set()
    for a in soup.find_all('a', href=True):
        url = urljoin(BASE, a['href'])
        parsed = urlparse(url)
        if 'mtgtop8.com' not in parsed.netloc or not parsed.path.rstrip('/').endswith('/event'):
            continue
        query = parse_qs(parsed.query)
        if not {'d', 'e'} <= query.keys():
            continue
        title = a.get_text(' ', strip=True)
        if not title or url in seen:
            continue
        # Prefere listas Affinity e variantes; a página do arquétipo pode
        # conter links de eventos e de decks de outros arquétipos.
        if 'affinity' not in normalize(title):
            continue
        seen.add(url)
        found.append((title, url))
        if len(found) >= limit:
            break
    return found


def parse_deck(soup):
    """Analisa somente a zona textual entre 'LANDS' e fim do 'SIDEBOARD'."""
    text = soup.get_text('\n', strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    main, side = Counter(), Counter()
    active = None
    started = False
    for line in lines:
        upper = line.upper()
        if upper == 'SIDEBOARD':
            active = 'side'
            started = True
            continue
        if re.fullmatch(r'\d+\s+(LANDS|CREATURES|INSTANTS AND SORC\.|OTHER SPELLS)', upper):
            active = 'main'
            started = True
            continue
        if not started or active is None:
            continue
        if upper.startswith(('AFFINITY DECKS', 'COMMENTS', 'SIMILAR DECKS', 'OTHER DECKS')):
            if active == 'side':
                break
        match = CARD.match(line)
        if match:
            qty, name = int(match.group(1)), match.group(2)
            if 1 <= qty <= 20 and not re.search(r'^(players|decks|cards)\b', name, re.I):
                (side if active == 'side' else main)[name] += qty
        # Sair após as 15 cartas de sideboard impede capturar cartas de outros decks.
        if sum(side.values()) >= 15:
            break
    return main, side


def parse_price(value):
    s = str(value or '').strip().replace('R$', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        result = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f'Preço inválido: {value!r}') from exc
    if result < 0:
        raise ValueError('Preço negativo')
    return result


def load_catalog(path):
    by_name = defaultdict(list)
    if not path.exists():
        raise FileNotFoundError(f'Catálogo não encontrado: {path}')
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        required = {'nome', 'preco', 'estoque', 'url'}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError('CSV exige colunas: nome;edicao;preco;estoque;url')
        for row in reader:
            name = (row.get('nome') or '').strip()
            if not name:
                continue
            stock = int(row.get('estoque') or 0)
            price = parse_price(row.get('preco'))
            if stock <= 0:
                continue
            by_name[normalize(name)].append({
                'nome': name, 'edicao': row.get('edicao', ''),
                'preco': price, 'estoque': stock, 'url': row.get('url', ''),
            })
    for options in by_name.values():
        options.sort(key=lambda x: x['preco'])
    return by_name


def quotes_for_card(card, qty, catalog):
    remaining = qty
    purchased = 0
    cost = Decimal('0')
    offers = []
    for option in catalog.get(normalize(card), []):
        selected = min(remaining, option['estoque'])
        if selected <= 0:
            continue
        cost += selected * option['preco']
        purchased += selected
        remaining -= selected
        offers.append((selected, option))
        if remaining == 0:
            break
    return purchased, remaining, cost, offers


def write_csv(path, cols, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description='Busca decks Pauper Affinity e calcula preços APENAS da loja.')
    parser.add_argument('--catalogo', default='catalogo_loja.csv', help='CSV exportado da Caverna do Basdão')
    parser.add_argument('--saida', default='resultados', help='Pasta de saída')
    parser.add_argument('--max-decks', type=int, default=10)
    parser.add_argument('--intervalo', type=float, default=2.0, help='Segundos entre requisições')
    parser.add_argument('--url-arquetipo', default=ARCHETYPE)
    args = parser.parse_args()
    output = Path(args.saida)
    output.mkdir(exist_ok=True, parents=True)
    catalog = load_catalog(Path(args.catalogo))
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        soup = fetch(session, args.url_arquetipo)
    except requests.RequestException as exc:
        sys.exit(f'Não foi possível acessar MTGTop8 ({exc}). Nenhum resultado inventado.')
    found = listing_decks(soup, args.max_decks)
    if not found:
        sys.exit('Nenhum link de deck Affinity detectado. Verifique se o layout do MTGTop8 mudou.')
    deck_rows, item_rows = [], []
    for title, url in found:
        time.sleep(max(0, args.intervalo))
        try:
            main_cards, side_cards = parse_deck(fetch(session, url))
        except requests.RequestException as exc:
            print(f'Ignorado {url}: {exc}', file=sys.stderr)
            continue
        m, s = sum(main_cards.values()), sum(side_cards.values())
        if m != 60 or s != 15:
            print(f'Ignorado (extração incompleta: main={m}, side={s}): {url}', file=sys.stderr)
            continue
        total_cost, obtained, missing = Decimal('0'), 0, 0
        for zone, cards in [('main', main_cards), ('sideboard', side_cards)]:
            for card, qty in sorted(cards.items()):
                bought, deficit, cost, offers = quotes_for_card(card, qty, catalog)
                obtained += bought
                missing += deficit
                total_cost += cost
                if offers:
                    for count, option in offers:
                        item_rows.append({
                            'deck': title, 'deck_url': url, 'secao': zone,
                            'carta': card, 'necessarias': qty, 'compraveis': bought,
                            'faltantes': deficit, 'qtd_oferta': count, 'edicao': option['edicao'],
                            'preco_unitario_R$': str(option['preco']),
                            'subtotal_R$': str(count * option['preco']), 'url_loja': option['url'],
                            'situacao': 'COMPLETA' if deficit == 0 else 'PARCIAL',
                        })
                else:
                    item_rows.append({
                        'deck': title, 'deck_url': url, 'secao': zone,
                        'carta': card, 'necessarias': qty, 'compraveis': 0,
                        'faltantes': deficit, 'qtd_oferta': 0, 'edicao': '',
                        'preco_unitario_R$': '', 'subtotal_R$': '0', 'url_loja': '',
                        'situacao': 'NAO ENCONTRADA',
                    })
        deck_rows.append({
            'deck': title, 'deck_url': url, 'main': m, 'sideboard': s,
            'cartas_disponiveis': obtained, 'cartas_faltantes': missing,
            'custo_parcial_R$': str(total_cost),
            'custo_total_R$': str(total_cost) if missing == 0 else '',
            'status': 'COMPLETO' if missing == 0 else 'INCOMPLETO',
        })
        print(f'{title}: {obtained}/75 cartas; custo cotado R$ {total_cost}; faltam {missing}')
    # Ordena decks completos por custo real, incompletos ao final (valor parcial não é preço do deck).
    deck_rows.sort(key=lambda row: (row['status'] != 'COMPLETO', Decimal(row['custo_parcial_R$'])))
    if not deck_rows:
        sys.exit('Nenhuma lista válida com 60 + 15 cartas foi extraída.')
    write_csv(output / 'comparacao_decks.csv', list(deck_rows[0]), deck_rows)
    write_csv(output / 'cartas_e_ofertas.csv', list(item_rows[0]), item_rows)
    print(f'Arquivos salvos em: {output.resolve()}')


if __name__ == '__main__':
    main()
