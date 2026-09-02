# Especificação do Projeto

## Visão geral

Sistema web responsivo para administração de empréstimos pessoais e uso de cartão de crédito, com histórico financeiro auditável e futura agenda de cobranças, WhatsApp e relatórios.

## Entidades principais

### Usuário

Responsável pelo acesso administrativo e registro de operações.

### Cliente

Cadastro com dados pessoais, contato, endereço, status e observações.

### Conta bancária

Pode pertencer ao administrador/sistema ou a um cliente. Guarda banco, agência, conta, tipo de conta, chave PIX, descrição e indicação de conta padrão.

### Empréstimo

Contrato independente vinculado a um cliente, com:

- valor original;
- saldo principal atual;
- taxa mensal;
- data do empréstimo;
- primeiro vencimento;
- dia de vencimento;
- status.

### Movimentação de empréstimo

Tipos:

- `EMPRESTIMO`;
- `JUROS`;
- `ABATIMENTO`;
- `QUITACAO`.

Inclui valor, data, competência quando aplicável, saldo anterior/posterior, usuário, conta origem/destino e snapshot bancário.

### Cartão de crédito

Cadastro independente dos empréstimos, vinculado ao cliente.

### Lançamento de cartão

Compra com descrição, valor total, quantidade de parcelas e data.

### Parcela de cartão

Valor, número da parcela, vencimento, status e informações de pagamento.

## Módulos já existentes

- autenticação e primeiro administrador;
- clientes;
- contas bancárias e PIX;
- empréstimos;
- juros;
- abatimentos;
- quitação;
- histórico de movimentações;
- dashboard financeiro;
- cartões de crédito;
- lançamentos parcelados;
- pagamento de parcelas.

## Próximos módulos previstos

- agenda de cobranças;
- mensagens de cobrança via WhatsApp;
- relatórios PDF/Excel;
- rotina de backup de dados;
- melhorias de auditoria e segurança.
