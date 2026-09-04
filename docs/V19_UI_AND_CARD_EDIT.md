# V19 — Revisão visual global e edição de lançamentos de cartão

## Interface

A V19 reorganiza o sistema visual sem trocar a estrutura funcional:

- container principal aumentado para até 1440 px;
- barra superior até 1480 px;
- menu horizontal compacto e com rolagem quando necessário;
- item ativo destacado;
- nomes abreviados no menu:
  - Movimentos;
  - Pg. integrados;
- tipografia de sistema menor e consistente;
- paddings de tabelas reduzidos;
- valores, badges e datas protegidos contra quebra inadequada;
- tabelas largas continuam com rolagem horizontal;
- paleta unificada em azul petróleo/slate com azul como ação principal.

## Impressão

Relatórios passam a solicitar:

```css
@page {
    size: A4 landscape;
    margin: 8mm;
}
```

As tabelas de relatório passam para `table-layout: fixed` somente na impressão,
com fonte reduzida e cabeçalho repetido em novas páginas.

## Cartões — alterar lançamento

Novo endpoint:

```text
/lancamentos-cartao/<id>/editar
```

Toda alteração exige:

- motivo;
- senha do usuário atualmente logado;
- auditoria com dados anteriores e posteriores.

### Sem parcelas pagas

Pode alterar:

- descrição;
- valor total;
- quantidade de parcelas;
- data da compra;
- primeiro vencimento.

As parcelas antigas são removidas e recriadas na mesma transação, usando
`split_centavos()` para preservar exatamente o valor total.

### Com parcela já paga

A estrutura financeira fica bloqueada para preservar histórico realizado.

Pode alterar:

- descrição.

Valor, quantidade, data e vencimentos ficam somente leitura.

A tela do cartão passa a mostrar botão `Alterar` em cada lançamento.
