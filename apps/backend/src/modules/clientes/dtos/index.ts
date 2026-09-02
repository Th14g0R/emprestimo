import { IsString, IsEmail, IsMobilePhone, IsOptional, IsEnum } from 'class-validator';

export class CreateClienteDto {
  @IsString()
  nome: string;

  @IsMobilePhone('pt-BR')
  telefone: string;

  @IsEmail()
  email: string;

  @IsString()
  cpf: string;

  @IsOptional()
  @IsString()
  endereco?: string;

  @IsOptional()
  @IsString()
  cidade?: string;

  @IsOptional()
  @IsString()
  estado?: string;

  @IsOptional()
  @IsString()
  cep?: string;

  @IsOptional()
  @IsString()
  observacoes?: string;

  @IsOptional()
  @IsEnum(['ativo', 'inativo'])
  status?: string;
}

export class UpdateClienteDto {
  @IsOptional()
  @IsString()
  nome?: string;

  @IsOptional()
  @IsMobilePhone('pt-BR')
  telefone?: string;

  @IsOptional()
  @IsEmail()
  email?: string;

  @IsOptional()
  @IsString()
  endereco?: string;

  @IsOptional()
  @IsString()
  cidade?: string;

  @IsOptional()
  @IsString()
  estado?: string;

  @IsOptional()
  @IsString()
  cep?: string;

  @IsOptional()
  @IsString()
  observacoes?: string;

  @IsOptional()
  @IsEnum(['ativo', 'inativo'])
  status?: string;
}
