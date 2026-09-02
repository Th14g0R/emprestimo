import { Injectable } from '@nestjs/common';
import { PrismaService } from '@/prisma/prisma.service';

@Injectable()
export class DashboardService {
  constructor(private prisma: PrismaService) {}

  async getMetricas() {
    const [
      totalEmprestado,
      saldoTotal,
      clientesAtivos,
      emprestimosAtivos,
      jurosPrevistos,
    ] = await Promise.all([
      this.getTotalEmprestado(),
      this.getSaldoTotal(),
      this.getClientesAtivos(),
      this.getEmprestimosAtivos(),
      this.getJurosPrevistos(),
    ]);

    return {
      totalEmprestado,
      saldoTotal,
      clientesAtivos,
      emprestimosAtivos,
      jurosPrevistos,
      timestamp: new Date(),
    };
  }

  private async getTotalEmprestado() {
    const result = await this.prisma.emprestimo.aggregate({
      _sum: {
        valor_original: true,
      },
    });
    return result._sum.valor_original || 0;
  }

  private async getSaldoTotal() {
    const result = await this.prisma.emprestimo.aggregate({
      _sum: {
        saldo_atual: true,
      },
    });
    return result._sum.saldo_atual || 0;
  }

  private async getClientesAtivos() {
    return this.prisma.cliente.count({
      where: { status: 'ativo' },
    });
  }

  private async getEmprestimosAtivos() {
    return this.prisma.emprestimo.count({
      where: { status: 'ativo' },
    });
  }

  private async getJurosPrevistos() {
    const emprestimos = await this.prisma.emprestimo.findMany({
      where: { status: 'ativo' },
      select: {
        saldo_atual: true,
        taxa_juros_mensal: true,
      },
    });

    return emprestimos.reduce((total, emp) => {
      return total + (emp.saldo_atual * emp.taxa_juros_mensal) / 100;
    }, 0);
  }
}
