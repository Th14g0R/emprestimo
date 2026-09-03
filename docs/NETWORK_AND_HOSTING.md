# Rede, acesso externo e hospedagem

## 1. Acesso na mesma rede local

No `Gerenciar-Emprestimo.bat`, use:

```text
4 - Configurar acesso/rede
2 - Rede local
```

O serviço será configurado para:

```text
0.0.0.0:5000
```

O Waitress escuta todas as interfaces locais. O Firewall do Windows recebe uma
regra TCP para a porta escolhida, apenas no perfil `Private` e apenas para
`LocalSubnet`.

Em outro computador da mesma rede, use:

```text
http://IP_DO_SERVIDOR:5000
```

Exemplo:

```text
http://192.168.1.50:5000
```

## 2. Acesso pela Internet

Não exponha diretamente Waitress/porta 5000 pela Internet em HTTP.

Opções recomendadas:

- VPN/Tailscale: mantém o sistema privado;
- reverse proxy HTTPS no mesmo servidor: Caddy, Nginx, Apache/IIS;
- hospedagem Python/WSGI.

Com reverse proxy no mesmo servidor, o Waitress pode continuar em
`127.0.0.1:5000`. O proxy recebe HTTPS 443 e encaminha internamente.

Configure no ambiente:

```text
EMPRESTIMO_HTTPS=1
EMPRESTIMO_BEHIND_PROXY=1
EMPRESTIMO_TRUSTED_HOSTS=seu-dominio.com,www.seu-dominio.com
SECRET_KEY=<chave-grande-e-aleatoria>
```

`ProxyFix` só deve ser habilitado quando realmente existir exatamente um proxy
confiável na frente da aplicação.

## 3. Hospedagem Web / WSGI

O projeto agora contém:

```text
wsgi.py
```

Entrypoints:

```python
from app import app
application = app
```

### PythonAnywhere / mod_wsgi

Aponte o WSGI para:

```text
wsgi:application
```

### Linux/VPS/Koyeb/Render com filesystem persistente

Instale:

```bash
pip install -r requirements.txt
pip install -r requirements-hosting.txt
```

Inicie, por exemplo:

```bash
gunicorn --bind 0.0.0.0:${PORT:-8000} wsgi:application
```

## 4. SQLite em hospedagem

SQLite exige armazenamento persistente.

O banco pode ser movido sem alterar código:

```text
EMPRESTIMO_DATA_DIR=/volume/persistente/emprestimo
```

ou:

```text
EMPRESTIMO_DATABASE=/volume/persistente/emprestimos.db
```

Não use SQLite em filesystem efêmero, pois o banco poderá desaparecer após
redeploy/restart do provedor.

## 5. `python app.py`

Continua disponível para desenvolvimento:

```text
EMPRESTIMO_HOST=0.0.0.0
EMPRESTIMO_PORT=5000
EMPRESTIMO_DEBUG=0
python app.py
```

Em produção prefira Waitress/serviço Windows ou WSGI do provedor.
