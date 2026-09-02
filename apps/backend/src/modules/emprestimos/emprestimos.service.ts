import { Injectable } from '@nestjs/common';
import { PrismaService } from '@/prisma/prisma.service';
import { CreateEmprestimoDto, AbatimentoDto } from './dtos';

@Injectable()
export class EmprestimosService {
  constructor(private prisma: PrismaService) {}

  async create(data: CreateEmprestimoDto) {
    const emprestimo = await this.prisma.emprestimo.create({
      data: {
        cliente_id: data.cliente_id,
        descricao: data.descricao,
        data_emprestimo: data.data_emprestimo,
        valor_original: data.valor_original,
        saldo_atual: data.valor_original,
        taxa_juros_mensal: data.taxa_juros_mensal,
        data_primeiro_vencimento: data.data_primeiro_vencimento,
        dia_vencimento: data.dia_vencimento,
      },
    });

    // Registra movimentação de empréstimo
    await this.prisma.movimentacaoEmprestimo.create({
      data: {
        emprestimo_id: emprestimo.id,
        tipo: 'EMPRESTIMO',
        data_movimento: new Date(),
        valor: data.valor_original,
      },
    });

    return emprestimo;
  }

  async findAll(page = 1, limit = 10) {
    const skip = (page - 1) * limit;
    const [data, total] = await Promise.all([
      this.prisma.emprestimo.findMany({
        skip,
        take: limit,
        include: {
          cliente: true,
          movimentacoes: true,
        },
      }),
      this.prisma.emprestimo.count(),
    ]);

    return {
      data,
      total,
      page,
      limit,
      pages: Math.ceil(total / limit),
    };
  }

  async findOne(id: string) {
    return this.prisma.emprestimo.findUnique({
      where: { id },
      include: {
        cliente: true,
        movimentacoes: true,
      },
    });
  }

  async abatimento(id: string, data: AbatimentoDto) {
    const emprestimo = await this.prisma.emprestimo.findUnique({
      where: { id },
    });

    if (!emprestimo) {
      throw new Error('Empréstimo não encontrado');
    }

    const novoSaldo = emprestimo.saldo_atual - data.valor;

    if (novoSaldo < 0) {
      throw new Error('Abatimento não pode ser maior que o saldo devedor');
    }

    // Atualiza saldo
    await this.prisma.emprestimo.update({
      where: { id },
      data: {
        saldo_atual: novoSaldo,
      },
    });

    // Registra movimentação
    return this.prisma.movimentacaoEmprestimo.create({
      data: {
        emprestimo_id: id,
        tipo: 'ABATIMENTO',
        data_movimento: new Date(),
        valor: data.valor,
        observacao: data.observacao,
      },
    });
  }

  async quitacao(id: string) {
    const emprestimo = await this.prisma.emprestimo.findUnique({
      where: { id },
    });

    if (!emprestimo) {
      throw new Error('Empréstimo não encontrado');
    }

    const valor_quitacao = emprestimo.saldo_atual;

    // Atualiza para quitado
    await this.prisma.emprestimo.update({
      where: { id },
      data: {
        saldo_atual: 0,
        status: 'quitado',
      },
    });

    // Registra movimentação de quitação
    return this.prisma.movimentacaoEmprestimo.create({
      data: {
        emprestimo_id: id,
        tipo: 'QUITACAO',
        data_movimento: new Date(),
        valor: valor_quitacao,
      },
    });
  }
}
