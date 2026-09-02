import { Injectable } from '@nestjs/common';
import { PrismaService } from '@/prisma/prisma.service';
import { CreateClienteDto, UpdateClienteDto } from './dtos';

@Injectable()
export class ClientesService {
  constructor(private prisma: PrismaService) {}

  async create(data: CreateClienteDto) {
    return this.prisma.cliente.create({
      data,
    });
  }

  async findAll(page = 1, limit = 10) {
    const skip = (page - 1) * limit;
    const [data, total] = await Promise.all([
      this.prisma.cliente.findMany({
        skip,
        take: limit,
        include: {
          emprestimos: true,
          cartoes: true,
        },
      }),
      this.prisma.cliente.count(),
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
    return this.prisma.cliente.findUnique({
      where: { id },
      include: {
        emprestimos: {
          include: {
            movimentacoes: true,
          },
        },
        cartoes: {
          include: {
            lancamentos: {
              include: {
                parcelas: true,
              },
            },
          },
        },
      },
    });
  }

  async update(id: string, data: UpdateClienteDto) {
    return this.prisma.cliente.update({
      where: { id },
      data,
    });
  }

  async delete(id: string) {
    return this.prisma.cliente.delete({
      where: { id },
    });
  }
}
