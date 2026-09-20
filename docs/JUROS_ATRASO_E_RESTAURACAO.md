# Juros de atraso e restauração do banco

## Regra implementada

O adicional incide sobre o juro mensal original do título:

```text
adicional = juro original × dias corridos de atraso ÷ 30
total = juro original + adicional
```

Exemplo: principal R$ 10.000,00 a 8% gera juro mensal de R$ 800,00.
Com 10 dias de atraso, o adicional é R$ 266,67 e o total R$ 1.066,67.
O valor diário não é arredondado antes da multiplicação. O principal não muda.

Ao reagendar novamente, o cálculo usa o mesmo valor original e o mesmo
vencimento-base. Não soma o adicional antigo nem cobra juros sobre ele.
Ao receber, usa a data efetiva do pagamento; a data da análise de um
comprovante não aumenta o atraso do cliente.

## Reagendamento

1. Em **A receber**, abra **Reagendar títulos em aberto**.
2. Selecione apenas os títulos que serão reagendados com cálculo de atraso.
   Pode selecionar vários títulos do mesmo cliente ou de contratos diferentes.
3. Informe uma nova data de pagamento, ou um dia mensal.
4. Se desejar mudar a agenda, marque **Aplicar o dia aos próximos títulos**.
   Os futuros não selecionados serão incluídos automaticamente na prévia;
   não é necessário selecioná-los junto com o título atrasado.
5. Clique em **Calcular e conferir prévia**. Confira valor original,
   vencimento-base, dias de atraso, adicional, total e nova data.
6. A prévia mostra separadamente os próximos títulos com seu valor mantido e
   adicional zero. Meses sem o dia escolhido usam seu último dia.
7. Informe motivo e senha e confirme as datas e valores.

Títulos vencidos não selecionados não mudam silenciosamente. Títulos futuros
que já possuem adicional próprio exigem conferência separada. A propagação
muda somente o dia dentro do mês de cada título; não desloca competências.

## Receber títulos

No título ou em **Registrar pagamento**, informe a data efetiva, selecione
os títulos e gere a prévia. Cada título usa seu vencimento-base individual.
O sistema soma os juros originais, os adicionais e o total. Alterar a data ou
a seleção exige nova conferência. Informe as contas e confirme.

O detalhamento fica no título, na movimentação, nos itens do pagamento e na
auditoria. A cobrança permanece um único lançamento JUROS por competência,
incluindo seu adicional. Pagamentos parciais continuam fora da regra atual.
Para corrigir a data de um recebimento já detalhado, estorne com senha/motivo
e registre novamente, conferindo a nova prévia.

## Posso trazer o banco antigo?

Bancos das versões compatíveis deste sistema recebem migrações incrementais.
A atualização acrescenta campos de detalhamento, sem recalcular pagamentos
já efetuados, saldos ou valores históricos. Um banco da versão original do
repositório e uma cópia do banco local foram validados em teste automatizado.
Isso não substitui a validação do seu arquivo específico, que ainda não foi
fornecido.

Primeiro valide uma cópia:

```sh
.venv-local/bin/python scripts/verificar_banco.py "/caminho/emprestimos.db"
```

Windows:

```bat
.venv\Scripts\python.exe scripts\verificar_banco.py "C:\backup\emprestimos.db"
```

A ferramenta abre a origem somente para leitura, gera uma cópia consistente
com a API de backup do SQLite e migra apenas a cópia temporária. Confere
integridade, relacionamentos e os valores/datas/status de cada registro
financeiro, não apenas a soma. Não substitui a origem nem o banco em uso.
Também informa duplicidades históricas, saldos parciais, ajustes antigos e
comprovantes que não foram encontrados.

### Cuidados na transferência

1. Pare o sistema de origem e o de destino antes de copiar arquivos manualmente.
   Não copie somente o `.db` de um sistema em execução: dados recentes podem
   estar no arquivo WAL. A ferramenta de verificação usa a API de backup para
   evitar esse problema durante a verificação.
2. Guarde uma cópia completa dos dados atuais e do banco a importar.
3. Para testar, use uma pasta `data/local-test` nova e vazia, preservando a
   pasta de teste anterior com outro nome. Coloque nela o banco com
   o nome `emprestimos.db`. O inicializador `teste_local.py` usa essa pasta.
4. Copie também `comprovantes/` para manter os arquivos enviados pelos clientes.
   O banco contém as referências, mas não contém os PDFs/imagens.
5. Pode preservar `.secret_key` da instalação anterior. Gerar uma nova chave
   encerra as sessões antigas, mas não muda os dados nem as senhas dos usuários.
6. Não reutilize arquivos `.db-wal`/`.db-shm` de outro banco: use a pasta nova.
7. Inicie, faça login com um usuário existente no banco restaurado e confira
   alguns clientes, contratos, saldos, pagamentos e comprovantes.

O caminho normal de `python app.py` é `data/emprestimos.db`; já o teste local
usa `data/local-test/emprestimos.db`. Configurações de ambiente podem mudar o
caminho normal. Não misture as duas instalações durante a conferência.

### Ajustes de versões anteriores

Se um título antigo já tem valor ajustado e não registra quanto era juro
original e quanto era adicional, o sistema não adivinha essa divisão. Ele
preserva o valor e pede conferência antes de calcular novo atraso. Confira o
juro original e o vencimento na correção do título (senha e auditoria) e só
então faça o novo reagendamento. Duplicidades e saldos parciais antigos também
permanecem preservados e exigem conferência; não são consolidados automaticamente.
