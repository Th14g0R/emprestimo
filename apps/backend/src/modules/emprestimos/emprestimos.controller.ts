import { Controller, Get, Post, Put, Delete, Param, Body, Query, UseGuards } from '@nestjs/common';
import { EmprestimosService } from './emprestimos.service';
import { CreateEmprestimoDto, AbatimentoDto } from './dtos';
import { JwtAuthGuard } from '../auth/jwt.guard';

@UseGuards(JwtAuthGuard)
@Controller('api/emprestimos')
export class EmprestimosController {
  constructor(private readonly emprestimosService: EmprestimosService) {}

  @Post()
  create(@Body() createEmprestimoDto: CreateEmprestimoDto) {
    return this.emprestimosService.create(createEmprestimoDto);
  }

  @Get()
  findAll(@Query('page') page?: number, @Query('limit') limit?: number) {
    return this.emprestimosService.findAll(page, limit);
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.emprestimosService.findOne(id);
  }

  @Post(':id/abatimento')
  abatimento(@Param('id') id: string, @Body() abatimentoDto: AbatimentoDto) {
    return this.emprestimosService.abatimento(id, abatimentoDto);
  }

  @Post(':id/quitacao')
  quitacao(@Param('id') id: string) {
    return this.emprestimosService.quitacao(id);
  }
}
