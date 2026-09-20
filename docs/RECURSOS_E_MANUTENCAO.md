# Espaço, desempenho e manutenção

Avaliação local de 19/09/2026. A aplicação continua sendo Flask + SQLite,
sem serviço de tarefas, frontend separado ou novos componentes de infraestrutura.

## Diagnóstico medido

Antes desta revisão, a pasta completa ocupava aproximadamente 40 MiB:

| Componente | Espaço local aproximado | Comportamento |
| --- | ---: | --- |
| Ambiente Python usado nos testes | 26 MiB | Dependências; não cresce por movimentação |
| Ambiente Python antigo do Windows | 6,5 MiB | Segunda instalação local; não executar/copiar ambas para produção |
| Backups das revisões anteriores | 4,9 MiB | Cresce a cada cópia guardada |
| Dados locais de teste | 304 KiB | Cresce com registros e comprovantes |
| Templates e arquivos estáticos | 216 KiB | Cresce somente quando o software muda |
| Cache Python | 428 KiB | Código compilado reutilizável; não é um arquivo novo por acesso |
| Git | 284 KiB | Histórico do código |
| Logs existentes | 8 KiB | Os arquivos encontrados são da publicação antiga |

O processo local de desenvolvimento apresentou 43.728 KiB de memória residente
(cerca de 42,7 MiB) e 0% de CPU na amostra em repouso. É uma fotografia local,
não uma garantia de consumo sob carga nem uma medição do serviço Windows.
Uploads simultâneos e relatórios extensos elevam o pico de memória.

## Refatoração aplicada

- A sincronização busca títulos abertos, sem carregar títulos encerrados para
  reconciliar pagamentos. Movimentos relacionados são consultados em lote.
- As previsões do mês corrente e dos dois seguintes são carregadas em lote;
  o histórico não é percorrido por uma consulta individual para cada previsão.
- Títulos automáticos só são regravados quando vencimento, valor, saldo-base ou
  taxa realmente mudam. Isso reduz escrita no SQLite/WAL e trabalho repetido.
- O gráfico do dashboard agrega apenas os seis meses exibidos.
- Removidas das dependências de instalação `openpyxl` e `reportlab`: nenhum
  código desta versão as utiliza. Os relatórios atuais são HTML. Os pacotes
  antigos foram mantidos no ambiente local; novas instalações deixam de
  instalar essas duas bibliotecas, que ocupavam juntas cerca de 6,1 MiB aqui.

As transações e os bloqueios que protegem o saldo foram preservados. A agenda
continua refletindo abatimentos, quitações e reagendamentos. Nenhuma tabela,
movimentação, auditoria ou imagem foi apagada. Não há nova migração de esquema
nesta revisão.

### Medição reproduzida em banco temporário

Cenário: 1.000 empréstimos ativos, 3.000 títulos automáticos, agenda já atualizada,
sem mudança financeira entre as duas sincronizações.

| Medida de uma sincronização | Antes | Depois |
| --- | ---: | ---: |
| Consultas SELECT | 9.002 | 5 |
| Linhas regravadas | 3.000 | 0 |
| Tempo local observado | 0,203 s | 0,173 s |

Os tempos são amostras, variam por máquina e não representam um teste de carga.
A redução determinística relevante é nas consultas e nas escritas desnecessárias.
A suíte inclui regressões para sincronizações repetidas sem gravações,
atualização após abatimento e preservação de títulos cancelados, além dos
cenários financeiros e de segurança existentes.

## O que cresce com o uso

**Comprovantes:** cada arquivo armazenado aceita até 3 MiB; imagens são reduzidas
e a entrada é limitada a 6 MiB. O limite individual não limita a pasta inteira.
Mil comprovantes no tamanho máximo ocupam aproximadamente 2,93 GiB, sem contar
backups. Arquivos vinculados a operações fazem parte do histórico; não devem ser
tratados como lixo. Eventuais arquivos sem referência após interrupção do servidor
precisam de conferência antes de exclusão.

**Banco e auditoria:** crescem com operações legítimas. A agenda gera somente uma
janela curta de previsões, não anos de parcelas de uma vez. SQLite pode reutilizar
páginas livres sem reduzir imediatamente o tamanho físico do arquivo. Não executar
VACUUM a cada acesso nem apagar arquivos WAL/SHM de um banco em uso.

**Backups:** não existe rotina de backups periódicos nesta aplicação. As cópias
criadas durante as revisões são manuais. No servidor, definir retenção no mecanismo
que fará o backup: por exemplo, sete diários e quatro semanais, com cópia externa
e restauração testada. Essa política é uma sugestão; não foi aplicada às cópias
existentes. Não incluir a pasta de backups dentro de cada novo backup.

**Logs:** a aplicação escreve os erros no logger padrão; não cria um arquivo por
requisição. A retenção do stdout/stderr depende de como o serviço Windows foi
instalado. Configurar rotação no gerenciador do serviço, por exemplo 5 arquivos de
10 MiB por fluxo, se suportado. O gerenciador de instalação mencionado no README
não está nesta cópia, portanto essa configuração não foi verificada nem alterada.

## Instalação enxuta e acompanhamento

1. Instalar apenas o código, templates, static e requirements em um único ambiente
   Python criado no Windows. Não copiar os ambientes do macOS, `data/local-test`,
   os backups de desenvolvimento ou caches de teste.
2. Usar um processo Waitress para o serviço `Emprestimo`, sem debug/reloader.
   Não manter também `python app.py` e o servidor de testes ativos em produção.
3. Manter banco, chave e comprovantes em diretório persistente. Backups devem
   incluir os comprovantes, além de uma cópia consistente do SQLite.
4. Acompanhar espaço livre, tamanho de dados/backups/logs e memória do processo
   no servidor real. Alertar antes de o volume encher; os limites por upload não
   substituem esse acompanhamento.
5. Limpeza de ambientes/caches antigos pode ser feita com o serviço parado após
   conferir qual ambiente ele utiliza. Não apagar `data`, `.secret_key`, auditoria
   ou comprovantes para liberar espaço sem uma política de retenção definida.

Ainda há listas e relatórios que carregam todos os resultados e sincronização
global em vários acessos. Para carteiras muito grandes, o próximo passo é medir
essas telas com uma cópia do volume real, paginar os históricos e restringir
consultas por contrato quando possível. Esta revisão não promete consumo
constante com crescimento ilimitado de dados ou usuários simultâneos.


## Publicação v2

O gerenciador Windows foi recuperado do repositório e incluído na versão 2,
com dependências atualizadas e branch release/v2. A configuração de logs do
WinSW usa rotação de 10 MiB e cinco arquivos por fluxo. Isso substitui a
limitação de inspeção registrada acima; o serviço Windows ainda exige
validação no sistema de destino.
