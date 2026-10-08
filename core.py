import io
import re
from collections import Counter
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

HEADERS = {'User-Agent': 'MTGLondrinaDeckPlanner/0.1 (educational; contact via repository)'}


def parse_deck(text):
    main, side = Counter(), Counter()
    current = main
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(('#', '//')):
            continue
        if re.match(r'^(sideboard|side deck|side)\s*:?$', line, re.I):
            current = side
            continue
        if re.match(r'^(mainboard|main deck|deck)\s*:?$', line, re.I):
            current = main
            continue
        if line.lower().startswith('sb:'):
            current_line = line[3:].strip()
            target = side
        else:
            current_line = line
            target = current
        match = re.match(r'^(\d+)\s*x?\s+(.+?)\s*$', current_line)
        if not match:
            continue
        qty, name = int(match.group(1)), match.group(2).strip()
        name = re.sub(r'\s+\([A-Z0-9]+\)\s+\d+[a-z]?$', '', name)
        if qty > 0 and name:
            target[name] += qty
    return main, side


def mtgtop8_deck(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('mtgtop8.com', 'www.mtgtop8.com') or parsed.path != '/event':
        raise ValueError('Informe uma URL HTTPS de deck MTGTop8 no formato /event?e=...&d=...')
    params = requests.utils.unquote(parsed.query)
    if not re.search(r'(?:^|&)d=\d+', params):
        raise ValueError('O link precisa conter o identificador d= do deck.')
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    # Older MTGTop8 layouts frequently expose raw lines separated by <br> and HTML tables.
    candidates = [soup.get_text('\n', strip=True)]
    for elem in soup.select('table, div'):
        text = elem.get_text('\n', strip=True)
        if 100 < len(text) < 15000 and re.search(r'(?m)^\d+\s+\S', text):
            candidates.append(text)
    best = (Counter(), Counter())
    for candidate in candidates:
        got = parse_deck(candidate)
        if sum(got[0].values()) + sum(got[1].values()) > sum(best[0].values()) + sum(best[1].values()):
            best = got
    if not 40 <= sum(best[0].values()) <= 100:
        raise ValueError('Não foi possível extrair um deck com segurança. Cole a lista no campo manual.')
    return best


def card_data(name):
    r = requests.get('https://api.scryfall.com/cards/named', params={'exact': name},
                     headers=HEADERS, timeout=12)
    if r.status_code == 404:
        r = requests.get('https://api.scryfall.com/cards/named', params={'fuzzy': name},
                         headers=HEADERS, timeout=12)
    r.raise_for_status()
    c = r.json()
    image = c.get('image_uris', {}).get('normal', '')
    if not image and c.get('card_faces'):
        image = c['card_faces'][0].get('image_uris', {}).get('normal', '')
    return {'name': c['name'], 'mana_value': float(c.get('cmc', 0)),
            'colors': c.get('color_identity', []), 'type_line': c.get('type_line', ''),
            'oracle_text': c.get('oracle_text', '\n'.join(f.get('oracle_text', '') for f in c.get('card_faces', []))),
            'pauper': c.get('legalities', {}).get('pauper', 'not_legal'), 'image': image,
            'scryfall_uri': c.get('scryfall_uri', '')}


def norm(s):
    return re.sub(r'\s+', ' ', str(s).strip()).casefold()


def inventory_price(rows, deck):
    """Greedy cheapest sourcing, respecting available quantities per row."""
    purchases, missing = [], []
    remaining_by_offer = {i: int(row["quantidade"]) for i, row in enumerate(rows)}
    for section, cards in deck.items():
        for name, needed in cards.items():
            eligible = sorted(((i, x) for i, x in enumerate(rows) if norm(x['carta']) == norm(name) and remaining_by_offer[i] > 0),
                              key=lambda item: float(item[1]['preco']))
            remaining = needed
            for i, x in eligible:
                taken = min(remaining, remaining_by_offer[i])
                if taken:
                    purchases.append({'secao': section, 'carta': name, 'loja': x['loja'],
                                      'quantidade': taken, 'preco_unitario': float(x['preco']),
                                      'total': round(taken * float(x['preco']), 2), 'url': x.get('url', '')})
                    remaining -= taken
                    remaining_by_offer[i] -= taken
                if remaining == 0:
                    break
            if remaining:
                missing.append({'secao': section, 'carta': name, 'quantidade': remaining})
    return purchases, missing


def similarity(original, candidate):
    if candidate['pauper'] != 'legal' or norm(original['name']) == norm(candidate['name']):
        return -1
    if 'Land' in original['type_line'] and 'Land' not in candidate['type_line']:
        return -1
    if 'Land' not in original['type_line'] and 'Land' in candidate['type_line']:
        return -1
    a = set(re.findall(r'[a-z]{4,}', original['oracle_text'].lower()))
    b = set(re.findall(r'[a-z]{4,}', candidate['oracle_text'].lower()))
    overlap = len(a & b) / max(1, len(a | b))
    type_a = set(original['type_line'].split(' — ')[0].split())
    type_b = set(candidate['type_line'].split(' — ')[0].split())
    type_score = len(type_a & type_b) / max(1, len(type_a | type_b))
    color_score = 1 if set(original['colors']) == set(candidate['colors']) else 0
    mana_score = max(0, 1 - abs(original['mana_value'] - candidate['mana_value']) / 5)
    return round(0.40 * overlap + 0.25 * type_score + 0.20 * color_score + 0.15 * mana_score, 3)
