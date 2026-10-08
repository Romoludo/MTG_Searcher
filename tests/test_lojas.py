import unittest
from lojas import parse_store_html, collect_piedade

HTML = '''<html><body><div>1920 itens encontrados.</div>
<div class="listing"><h3>Zagaieiro Arconexo</h3><p>Arcbound Javelineer MH2</p><span>SP</span><div>13 Un. R$ 0,35</div><a href="/magic/produto/123/carta">Comprar</a></div>
<div class="listing"><h3>Rateiro Arconexo</h3><p>Arcbound Mouser MH2</p><div>17 Un. R$ 0,35</div><a href="/magic/produto/124/carta">Comprar</a></div></body></html>'''

class FakeResponse:
    status_code = 200
    text = HTML
    def raise_for_status(self): pass
class FakeSession:
    def get(self, url, **kwargs): return FakeResponse()

class StoreTests(unittest.TestCase):
    def test_parse_cards(self):
        offers, info = parse_store_html(HTML)
        self.assertEqual(len(offers), 2)
        self.assertEqual(offers[0]['carta'], 'Arcbound Javelineer')
        self.assertEqual(offers[0]['quantidade'], 13)
        self.assertEqual(offers[0]['preco'], 0.35)
        self.assertEqual(info['total_informado_site'], 1920)
    def test_partial_does_not_claim_full(self):
        offers, meta = collect_piedade(1, session=FakeSession())
        self.assertEqual(len(offers), 2)
        self.assertFalse(meta['completo'])
    def test_no_guess_from_translated_title(self):
        html = '<div><h3>Nome em Português</h3><span>SP</span><b>3 Un. R$ 1,00</b></div>'
        offers, _ = parse_store_html(html)
        self.assertEqual(offers, [])

if __name__ == '__main__': unittest.main()
