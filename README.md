# MTG Londrina — Pauper (MVP)

Streamlit para carregar decklists Pauper do MTGTop8 (tentativa de extração de URL) ou coladas manualmente, importar inventário de **lojas físicas de Londrina**, respeitar quantidades, comparar custo com orçamento e sugerir substituições usando Scryfall.

## Execução local

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Publicação

1. Crie um repositório no GitHub e envie todos os arquivos desta pasta para a raiz.
2. Entre em https://share.streamlit.io/ e selecione **Create app**.
3. Escolha o repositório, branch `main`, arquivo `app.py` e **Deploy**.
4. Recomenda-se Python 3.12.

## Modelo de inventário

CSV com cabeçalhos `loja,carta,quantidade,preco,url`. `preco` em reais (use ponto decimal, por exemplo `1.50`). Somente lojas físicas de Londrina, preços e estoque verificados manualmente, sem inventar ofertas.

## Limitações conscientemente preservadas

- MTGTop8 pode alterar HTML ou bloquear requisições. O importador URL é **experimental**; colar decklist é o caminho confiável.
- Não há conector oficial de estoque das lojas cadastrado: nenhuma oferta aparece até alimentar o CSV. Isso evita preço fictício.
- Os dados de inventário são mantidos só na sessão Streamlit e devem ser exportados em CSV.
- O valor parcial de ofertas não é apresentado como preço do deck completo quando faltam cartas.
- A similaridade é heurística e consulta somente cartas disponíveis no CSV (até 30 nomes distintos por rodada); não garante equivalência tática nem custo ótimo sob limite de lojas.
- A montagem não valida inteiramente regras de deck e bans; confirma legalidade Pauper das alternativas consultadas no Scryfall.
- Para volumes grandes de consultas Scryfall, implemente bulk data e controle de taxa antes de uso em produção.
- Sem estimativa de frete (compra presencial).

## Atualização de preços da Piedade (versão 0.2)

Na aba **2 · Estoque local**, clique em **Atualizar preços da Piedade**. O aplicativo lê até cinco páginas públicas do catálogo e permite baixar as ofertas obtidas em CSV. Não é necessário criar um arquivo manual para testar o fluxo.

**Limitações essenciais:** o site usa carregamento progressivo, pode exigir JavaScript, mudar sua estrutura ou negar acesso a hosts em nuvem. Esta integração é *best effort* e não acessa APIs privadas, não contorna proteções e **não garante coleta integral dos anúncios**. Se falhar, utilize o CSV fornecido pela loja ou preencha a tabela. O botão guarda os dados apenas na sessão; exporte o CSV para não perdê-los. Confirme os estoques com a loja antes de comprar. Para uso recorrente, solicite à loja acesso autorizado a um feed estruturado.

O coletor está em `lojas.py` e seus testes em `tests/test_lojas.py`. Não altere a URL da loja para vendedores de fora de Londrina sem verificar sua localização física.
