import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { JwtModule } from '@nestjs/jwt';
import { PrismaModule } from './prisma/prisma.module';
import { AuthModule } from './modules/auth/auth.module';
import { ClientesModule } from './modules/clientes/clientes.module';
import { EmprestimosModule } from './modules/emprestimos/emprestimos.module';
import { CartaoModule } from './modules/cartao/cartao.module';
import { DashboardModule } from './modules/dashboard/dashboard.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),
    JwtModule.register({
      global: true,
      secret: process.env.JWT_SECRET || 'your-secret-key',
      signOptions: { expiresIn: process.env.JWT_EXPIRATION || '7d' },
    }),
    PrismaModule,
    AuthModule,
    ClientesModule,
    EmprestimosModule,
    CartaoModule,
    DashboardModule,
  ],
  controllers: [],
  providers: [],
})
export class AppModule {}
