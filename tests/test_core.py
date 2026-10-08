import unittest
from core import parse_deck, inventory_price, similarity

class Tests(unittest.TestCase):
    def test_parse(self):
        m, s = parse_deck('4 Frogmite\n2 Myr Enforcer\nSideboard\n3 Hydroblast')
        self.assertEqual(m['Frogmite'], 4)
        self.assertEqual(s['Hydroblast'], 3)

    def test_inventory(self):
        rows = [{'loja':'A','carta':'Frogmite','quantidade':2,'preco':1.0},
                {'loja':'B','carta':'Frogmite','quantidade':3,'preco':2.0}]
        buys, missing = inventory_price(rows, {'Principal': {'Frogmite': 4}})
        self.assertEqual(sum(p['total'] for p in buys), 6)
        self.assertFalse(missing)

    def test_not_pauper(self):
        base = {'name':'A','pauper':'legal','type_line':'Creature','oracle_text':'Draw a card', 'colors':['U'], 'mana_value':2}
        other = dict(base, name='B', pauper='not_legal')
        self.assertEqual(similarity(base,other),-1)

if __name__ == '__main__':
    unittest.main()
