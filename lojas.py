"""Coleta prudente de anúncios públicos da loja Piedade no MYP Cards.

Não contorna login, captcha, bloqueio ou proteções. Um resultado parcial nunca
é apresentado como inventário completo. A página pode mudar sem aviso.
"""
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

STORE_URL = 'https://mypcards.com/piedade/magic'
STORE_NAME = 'Piedade Card House'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; MTGLondrina/0.2; personal deck research)'}
COLUMNS = ['loja', 'carta', 'quantidade', 'preco', 'url']
PRICE = re.compile(r'R\$\s*([\d.]+,\d{2})')
QTY = re.compile(r'(?<!\d)(\d{1,5})\s*(?:Un\.|un\.|unidades?)', re.I)
EDITION = re.compile(r'\s+(?:[A-Z0-9]{2,6})$')
CONDITIONS = {'NM', 'SP', 'MP', 'HP', 'DM', 'Foil', 'Normal', 'Etched Foil'}


def parse_brl(s):
    return float(Decimal(s.replace('.', '').replace(',', '.')))


def _candidate_blocks(soup):
    """Seek compact product nodes; avoid collecting parent containers repeatedly."""
    found = []
    for node in soup.find_all(['li', 'article', 'div']):
        text = node.get_text(' ', strip=True)
        if not (QTY.search(text) and PRICE.search(text)) or len(text) > 650:
            continue
        if any(ch.find(['h3', 'h4']) and QTY.search(ch.get_text(' ', strip=True)) and PRICE.search(ch.get_text(' ', strip=True))
               for ch in node.find_all(['li', 'article', 'div'], recursive=False)):
            continue
        if not node.find(['h3', 'h4', 'a']):
            continue
        found.append(node)
    return found


def parse_store_html(html, page_url=STORE_URL):
    """Extract offers, only when English name, quantity and BRL price are detectable.

    Returns (offers, diagnostics). Duplicate advertisements are NOT combined.
    """
    soup = BeautifulSoup(html, 'html.parser')
    offers = []
    seen = set()
    for block in _candidate_blocks(soup):
        lines = [x.strip() for x in block.stripped_strings if x.strip()]
        if not lines:
            continue
        raw = ' '.join(lines)
        q = QTY.search(raw)
        p = PRICE.search(raw)
        if not q or not p:
            continue
        headings = [x.get_text(' ', strip=True) for x in block.select('h3, h4')]
        # The storefront displays Portuguese display title followed by English card name + edition.
        # Locate the second heading's next textual line, NOT the translated display title.
        candidate = None
        for h in headings:
            try:
                idx = next(i for i, v in enumerate(lines) if v == h)
            except StopIteration:
                continue
            if idx + 1 < len(lines):
                nxt = lines[idx + 1]
                if nxt and not QTY.search(nxt) and not PRICE.search(nxt) and nxt not in CONDITIONS:
                    candidate = nxt
                    break
        if not candidate:
            continue  # Do not guess translated/localized names.
        candidate = EDITION.sub('', candidate).strip()
        if not candidate or len(candidate) > 115 or candidate.lower() in ('comprar', 'adicionar a lista de desejos'):
            continue
        qty = int(q.group(1))
        value = parse_brl(p.group(1))
        if qty < 1 or value < 0:
            continue
        link = ''
        for a in block.find_all('a', href=True):
            href = urljoin(page_url, a['href'])
            parsed = urlparse(href)
            if parsed.hostname in ('mypcards.com', 'www.mypcards.com') and ('/produto/' in parsed.path or '/magic/' in parsed.path):
                link = href
                break
        if not link:
            link = page_url  # Seller listing link, not a product link.
        # Exact blocks of the same offer can repeat due to layout. Preserve different offers.
        signature = (candidate.casefold(), qty, value, link)
        if signature in seen:
            continue
        seen.add(signature)
        offers.append(dict(loja=STORE_NAME, carta=candidate, quantidade=qty, preco=value, url=link))
    count = soup.get_text(' ', strip=True)
    total_match = re.search(r'([\d.]+)\s+itens encontrados', count, re.I)
    reported_total = int(total_match.group(1).replace('.', '')) if total_match else None
    return offers, {'anuncios_exibidos': len(offers), 'total_informado_site': reported_total}


def collect_piedade(max_pages=3, delay_seconds=1.0, session=None):
    """Best-effort public listing fetch. Never claims complete stock."""
    client = session or requests.Session()
    max_pages = max(1, min(int(max_pages), 5))
    records, unique, diagnostics = [], set(), []
    for page in range(1, max_pages + 1):
        url = STORE_URL if page == 1 else f'{STORE_URL}?page={page}'
        try:
            resp = client.get(url, headers=HEADERS, timeout=18)
            if resp.status_code in (401, 403, 429):
                raise RuntimeError(f'Acesso negado ou limitado pelo site (HTTP {resp.status_code}). Não tente contornar o bloqueio.')
            resp.raise_for_status()
            offers, info = parse_store_html(resp.text, url)
        except requests.RequestException as exc:
            if not records:
                raise RuntimeError(f'Não foi possível consultar a loja: {exc}') from exc
            diagnostics.append({'pagina': page, 'erro': str(exc)})
            break
        for x in offers:
            identity = tuple(x[k] for k in COLUMNS)
            if identity not in unique:
                unique.add(identity)
                records.append(x)
        diagnostics.append({'pagina': page, **info})
        if not offers:
            break
        if page < max_pages:
            time.sleep(max(0.8, float(delay_seconds)))
    return records, {'consultado_em_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                     'anuncios_lidos': len(records), 'paginas': diagnostics,
                     'completo': False,
                     'aviso': 'Leitura parcial de páginas públicas; não garante todos os anúncios nem estoque atualizado.'}
