#!/usr/bin/env bash
# Instala/atualiza e (re)inicia os serviços Celery (worker + beat) com o código atual.
# Idempotente. Roda no deploy (passo 8/8) e também à mão, no servidor:
#
#     sudo bash deploy/celery-servicos.sh
#
# Código de saída: 0 = tudo ativo | 1 = algum problema (veja as linhas "### AVISO").
# O log completo fica em backups/celery-servicos.log.

cd "$(dirname "$0")/.." || exit 2
APP_DIR="$(pwd)"
mkdir -p backups
LOG="$APP_DIR/backups/celery-servicos.log"
exec > >(tee "$LOG") 2>&1          # tudo que aparece na tela também vai para o arquivo

SERVICOS="buscalicitacoes-worker buscalicitacoes-beat"
AVISOS=0
aviso() { echo "### AVISO: $*"; AVISOS=1; }

# Root não precisa de sudo; os demais precisam de sudo sem senha.
SUDO=""
if [ "$(id -u)" != 0 ]; then
  SUDO="sudo -n"
  if ! $SUDO true 2>/dev/null; then
    aviso "usuário '$(id -un)' sem sudo sem senha: não dá para instalar/reiniciar os serviços."
    exit 1
  fi
fi
command -v systemctl >/dev/null 2>&1 || { aviso "systemctl não encontrado."; exit 1; }

echo "usuário: $(id -un) | diretório: $APP_DIR"

# Redis pode ter outro nome de serviço (redis-server, redis) ou rodar fora do systemd:
# o que importa é aceitar conexões.
if systemctl is-active --quiet redis-server || systemctl is-active --quiet redis \
   || (exec 3<>/dev/tcp/127.0.0.1/6379) 2>/dev/null; then
  echo "Redis: ok (porta 6379 responde)"
else
  aviso "Redis não responde em 127.0.0.1:6379 (nem redis-server nem redis estão ativos). Veja deploy/LEIA-ME.md."
  exit 1
fi

# nomes antigos (se algum dia existiram) saem de cena
for u in celery-worker celery-beat; do
  if [ -f "/etc/systemd/system/$u.service" ]; then
    echo "removendo unidade antiga $u"
    $SUDO systemctl disable --now "$u" 2>&1 | tail -1
  fi
done

RELOAD=0
for u in $SERVICOS; do
  src="deploy/systemd/$u.service"; dst="/etc/systemd/system/$u.service"
  if [ ! -f "$src" ]; then aviso "$src não existe no repositório."; continue; fi
  if ! $SUDO cmp -s "$src" "$dst"; then
    if $SUDO cp "$src" "$dst"; then
      echo "$u: unidade instalada/atualizada"; RELOAD=1
    else
      aviso "não consegui copiar $src para $dst."
    fi
  fi
done
if [ "$RELOAD" = 1 ]; then
  $SUDO systemctl daemon-reload || aviso "systemctl daemon-reload falhou."
fi

for u in $SERVICOS; do
  $SUDO systemctl enable "$u" >/dev/null 2>&1
  $SUDO systemctl restart "$u" || aviso "systemctl restart $u falhou."
done

sleep 6
for u in $SERVICOS; do
  if systemctl is-active --quiet "$u"; then
    echo "$u: ativo"
  else
    aviso "$u não está ativo. Estado e últimas linhas do log:"
    $SUDO systemctl status "$u" --no-pager -n 0 2>&1 | head -12
    $SUDO journalctl -u "$u" -n 30 --no-pager 2>&1
  fi
done

[ "$AVISOS" = 0 ] && echo "Celery: worker e beat ativos." || echo "Celery: com problemas (veja os avisos acima)."
exit "$AVISOS"
