#!/bin/bash
set -e
cd "$(dirname "$0")"
for candidato in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        exec "$candidato" scripts/gerenciar_macos.py "$@"
    fi
done
printf '%s\n' 'Instale Python 3.10 ou superior pelo python.org e tente novamente.'
read -r -p 'Pressione Enter para fechar. '
exit 1
