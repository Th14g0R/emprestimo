import { IsString, IsNumber, IsDate, IsEnum, IsOptional } from 'class-validator';
import { Type } from 'class-transformer';

export class CreateEmprestimoDto {
  @IsString()
  cliente_id: string;

  @IsString()
  descricao: string;

  @IsDate()
  @Type(() => Date)
  data_emprestimo: Date;

  @IsNumber()
  valor_original: number;

  @IsNumber()
  taxa_juros_mensal: number;

  @IsDate()
  @Type(() => Date)
  data_primeiro_vencimento: Date;

  @IsNumber()
  dia_vencimento: number;
}

export class UpdateEmprestimoDto {
  @IsOptional()
  @IsString()
  descricao?: string;

  @IsOptional()
  @IsEnum(['ativo', 'quitado', 'vencido'])
  status?: string;
}

export class AbatimentoDto {
  @IsNumber()
  valor: number;

  @IsOptional()
  @IsString()
  observacao?: string;
}
