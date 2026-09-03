# HOTFIX V9 — Serviço Windows / Waitress

## Sintoma

A instalação concluía, criava o serviço `Emprestimo`, porém o Windows retornava
erro 1067 ao iniciá-lo.

Um teste manual com:

```text
python app.py
```

também podia retornar `No module named flask`, mas esse teste utiliza o Python
global e não o ambiente virtual do projeto.

O teste correto é:

```text
.venv\Scripts\python.exe app.py
```

## Alterações

### 1. Runner próprio do serviço

O serviço não executa mais `waitress-serve.exe` diretamente. O instalador gera:

```text
service\service_runner.py
```

e o WinSW executa:

```text
.venv\Scripts\python.exe service\service_runner.py
```

O runner importa `waitress` e `app` explicitamente e chama `waitress.serve()`.

### 2. Conta do serviço

A versão V9 usa `LocalSystem`.

Motivo: o `venv` foi criado sobre um Python-base que pode estar instalado em um
perfil de usuário (`C:\Users\...\AppData\...`). Um `venv` mantém a referência
ao Python-base em `pyvenv.cfg`. `LocalService` pode não ter acesso ao Python-base
do perfil que criou o ambiente.

Essa escolha simplifica a instalação. Como mitigação, o modo padrão do site
continua limitado a `127.0.0.1`.

### 3. Reinstalação determinística do wrapper

Na instalação/atualização, o serviço anterior é parado e removido antes da
instalação da nova configuração.

### 4. Diagnóstico

Se o serviço não iniciar, o instalador exibe automaticamente os logs mais
recentes da pasta:

```text
logs\
```

e não exibe mais "Instalação concluída" se o serviço ou `/health` falhar.

### 5. Validação adicional

Antes de instalar o serviço:

- Flask/Waitress/openpyxl/reportlab são importados dentro da `.venv`;
- `service_runner.py --check` é executado;
- a porta configurada é verificada.

## Teste manual correto

Dentro da pasta instalada:

```bat
.venv\Scripts\python.exe -c "import flask,waitress,app"
```

Para executar o servidor manualmente:

```bat
.venv\Scripts\python.exe service\service_runner.py --host 127.0.0.1 --port 5000
```


## Compatibilidade com WinSW 2.12

A configuração foi mantida deliberadamente mínima e compatível com o modo
"bundled" do WinSW 2.12: `EmprestimoService.exe` e
`EmprestimoService.xml` permanecem lado a lado.

O serviço é removido antes do teste de porta e reinstalado depois, garantindo
que reparos não falhem apenas porque a versão anterior ainda estava ocupando a
porta.
