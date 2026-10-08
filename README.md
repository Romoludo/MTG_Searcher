# Magic Deck Finder — versão web

Aplicativo Streamlit para identificar até 10 decks Pauper Affinity no MTGTop8 e comparar seus custos usando **exclusivamente** um catálogo CSV da Caverna do Basdão.

## Publicar gratuitamente no Streamlit Community Cloud

1. Crie um repositório no GitHub e envie **app.py**, **bot_magic.py**, **requirements.txt** e **catalogo_loja_modelo.csv** na raiz.
2. Acesse https://share.streamlit.io/ e conecte sua conta GitHub.
3. Selecione o repositório, informe `app.py` como arquivo principal e publique.
4. Abra o endereço web gerado, importe um CSV de estoque/preço da loja e clique em **Buscar decks e comparar**.

Não é necessário manter o computador ligado depois da publicação, mas a hospedagem pode entrar em suspensão por inatividade.

## Teste local opcional

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Formato CSV da loja

Separador `;`; colunas `nome;edicao;preco;estoque;url`. Aceita preço no formato `4,50` ou `4.50`. Cada linha é uma oferta de carta/edição. Não use os dados fictícios do CSV modelo para decisões de compra.

## Limitações

- O site da Caverna do Basdão não é consultado diretamente devido ao bloqueio 403. É preciso obter um CSV legítimo ou uma API autorizada.
- O MTGTop8 pode alterar páginas; se isso acontecer, o extrator precisa de ajustes.
- Se a consulta falhar, o app exibe um erro em vez de inventar preços ou resultados.
- Estoques são considerados em cada deck, individualmente; os resultados não representam compra simultânea de vários decks.
- O app aceita uma URL de arquétipo MTGTop8; o padrão é Affinity Pauper.
