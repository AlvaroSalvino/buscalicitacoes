# Atualização automática em produção (Celery + Redis)

O que roda sozinho, todos os dias, sem ninguém acionar:

| Quando | O que |
|---|---|
| A cada minuto | `agendar_syncs` olha cada fonte e dispara o sync das que venceram o intervalo (PNCP 60 min, TCE-PI 2 h, TCE-MA 6 h, TCE-CE 24 h) |
| 03:30 | `encerrar_vencidas`: licitações com prazo vencido viram "encerrada" |
| 04:00 | `limpar_logs_antigos`: apaga logs de sync com mais de 60 dias |
| Após cada sync | `match_licitacoes` cruza as licitações novas com os alertas e envia e-mail/push |

Processos (systemd): `buscalicitacoes-worker` (executa) e `buscalicitacoes-beat` (agenda, **só uma instância**).
Os arquivos `.service` estão em `deploy/systemd/` e o `deploy.yml` os instala/reinicia a cada push.

## Configuração única no servidor

1. **Redis** (se ainda não houver): `sudo apt install redis-server` e `sudo systemctl enable --now redis-server`.
2. **`.env` de produção** (Redis é compartilhado com outros projetos: use bancos/prefixo próprios):
   ```
   CELERY_BROKER_URL=redis://127.0.0.1:6379/5
   CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/6
   # opcionais (já têm padrão): CELERY_QUEUE=buscalicitacoes  CELERY_KEY_PREFIX=buscalic:
   ```
   (o `redis://redis:6379/0` do `.env.example` é do Docker e **não funciona** no servidor).
3. Primeiro deploy depois disso instala e liga os dois serviços sozinho.

## Conferir

```bash
systemctl status buscalicitacoes-worker buscalicitacoes-beat
journalctl -u buscalicitacoes-beat -n 30 --no-pager     # deve mostrar "Scheduler: Sending due task..."
journalctl -u buscalicitacoes-worker -n 50 --no-pager   # deve mostrar "Task integracoes.tasks.sync_fonte ... succeeded"
redis-cli -n 5 ping
```
No app: **Conta → "Atualização automática"** (só superusuário) mostra, por fonte, a última execução, quando é a próxima, o total de licitações e avisa se alguma está atrasada. Há também o botão "Sincronizar agora".

## Pontos de atenção

- **SQLite + Celery gravando**: funciona (WAL, timeout 30 s, worker e Apache com o mesmo usuário), mas **MySQL é o recomendado** para produção (`DB_ENGINE=mysql` no `.env`).
- Nunca rode `manage.py` como root; use `sudo -u www-data` (senão o dono dos arquivos do SQLite muda e o banco corrompe).
- Para forçar um sync manual: `sudo -u www-data venv/bin/python manage.py sync_fonte <id>` (ids: 1 PNCP, 2 TCE-PI, 3 TCE-MA, 4 TCE-CE).
- Fonte travada em "em_execucao" por mais de 2 h é marcada como erro automaticamente e refeita.
