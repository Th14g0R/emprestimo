export type Cliente = {
  id: string;
  nome: string;
  telefone: string;
  email: string;
  cpf: string;
  endereco?: string;
  cidade?: string;
  estado?: string;
  cep?: string;
  observacoes?: string;
  status: 'ativo' | 'inativo';
  created_at: Date;
  updated_at: Date;
};

export type Emprestimo = {
  id: string;
  cliente_id: string;
  descricao: string;
  data_emprestimo: Date;
  valor_original: number;
  saldo_atual: number;
  taxa_juros_mensal: number;
  data_primeiro_vencimento: Date;
  dia_vencimento: number;
  status: 'ativo' | 'quitado' | 'vencido';
  created_at: Date;
  updated_at: Date;
};

export type MovimentacaoEmprestimo = {
  id: string;
  emprestimo_id: string;
  tipo: 'EMPRESTIMO' | 'JUROS' | 'ABATIMENTO' | 'QUITACAO';
  data_movimento: Date;
  valor: number;
  observacao?: string;
  created_at: Date;
};

export type CartaoCredito = {
  id: string;
  cliente_id: string;
  descricao: string;
  created_at: Date;
};

export type ParcelaCartao = {
  id: string;
  numero_parcela: number;
  valor: number;
  vencimento: Date;
  data_pagamento?: Date;
  status: 'pendente' | 'pago' | 'vencido';
};
