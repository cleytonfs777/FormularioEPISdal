# Painel administrativo — fluxo de aprovação

## O que mudou

A extensão continua salvando no SQLite ao clicar em **Enviar Formulário**.
A única exceção: mudar um item de **POSSUI** para **NÃO POSSUI**.
Essa troca vira uma **solicitação pendente**. Um admin autentica no painel,
vê o diff e aprova (grava no banco) ou rejeita (com motivo).

Alterações comuns (medidas, conservação, NÃO POSSUI → POSSUI, etc.)
entram na hora e vão para a trilha de auditoria com origem `direta`.

## Autenticação

Sessão em cookie **HttpOnly** + token **CSRF** nos POSTs do painel.
Não usamos JWT: o admin é SSR (Jinja). Sessão invalida no logout e
não fica token no JavaScript.

## Docker

Na pasta `api/`:

```bash
docker compose up --build
```

Ou na raiz do repositório:

```bash
docker compose up --build
```

- API e painel: `http://localhost:8000`
- Login admin: `http://localhost:8000/admin/login`
- SQLite persiste no volume `epi-data` (`/data/epi.db` no container)
- Credenciais do admin: só `ADMIN_USERNAME` e `ADMIN_PASSWORD` em `api/.env` (o compose não define senha)
- Planilha: `SPREADSHEET_ID`, `GOOGLE_CREDENTIALS_FILE` e `HTTPS_PROXY` vêm do `api/.env`

## Railway

O `Dockerfile` da raiz e o `railway.toml` sobem a API. No serviço da Railway:

1. Volume persistente montado em `/data` (o SQLite fica em `/data/epi.db`).
2. Variáveis (não copie o proxy da Prodemge):

```
DATABASE_URL=sqlite:////data/epi.db
SQLITE_JOURNAL_MODE=DELETE
ADMIN_USERNAME=admin
ADMIN_PASSWORD=uma-senha-com-8-ou-mais
SESSION_SECRET=uma-string-longa-aleatoria
SECRET_CODE=outro-segredo
SPREADSHEET_ID=id-da-planilha
SHEET_NAME=Relação Nominal
SYNC_INTERVAL_SECONDS=300
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
HTTPS_PROXY=
```

`GOOGLE_CREDENTIALS_JSON` é o conteúdo de `service_account.json` em uma linha. A Railway define `PORT` e `RAILWAY_ENVIRONMENT`; o cookie do painel sai com `Secure` só nesse ambiente. O primeiro boot cria o admin e o sync enche o banco a partir da planilha.

A extensão Chrome continua apontando para `http://localhost:8000`.

## Sync com a planilha

A cada **5 minutos** (ou `POST /sync`) o ciclo é:

1. Planilha → SQLite (novos militares e identificação; não apaga o que está `dirty`).
2. SQLite → planilha: só quem o formulário/admin alterou (`dirty=1`).

A service account do `service_account.json` precisa de permissão **Editor** na planilha.
`SYNC_INTERVAL_SECONDS=300` no `.env`.

## Migração (sem Docker)

Na pasta `api/`:

```bash
pip install -r requirements.txt
alembic upgrade head
python create_admin.py admin SuaSenhaAqui
py -3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`init_db()` na subida da API também cria as tabelas se ainda não existirem
(útil em SQLite de desenvolvimento). Se o Alembic reclamar que a tabela já
existe, marque a revisão como aplicada:

```bash
alembic stamp 0001_admin
```

No `.env`, defina `SESSION_SECRET` (string longa e aleatória).

## Uso

1. Militar preenche o formulário na extensão e envia.
2. Se só houve alteração comum: status `gravado`.
3. Se houve POSSUI → NÃO POSSUI: status `pendente` (as demais mudanças já gravadas).
4. Admin abre `http://127.0.0.1:8000/admin/login`.
5. Em **Pendentes**, abre a solicitação, aprova ou rejeita.
6. **Histórico** lista tudo o que efetivamente mudou no SQLite.

## Endpoints

| Método | Rota | Quem |
|---|---|---|
| POST | `/api/alteracoes` | Extensão (só os campos que mudaram) |

Body: `{ "num_bm": "...", "alteracoes": [{ "campo": "tam_coturno", "valor_novo": "42" }] }`.

Resposta `status`: `gravado` | `pendente` | `sem_alteracao`. Sem diff não há `COMMIT`.
| GET | `/consulta/avisos?q=` | Avisos pendentes do militar |
| POST | `/consulta/avisos/{id}/lida?q=` | Descarta aviso após leitura |
| GET | `/sync` | Status (pendentes dirty + último ciclo) |
| POST | `/sync` | Sincroniza agora (planilha ↔ SQLite) |
| POST | `/sync/force` | Idem, exige `X-Secret-Code` |
| GET/POST | `/admin/login` | Admin |
| POST | `/admin/logout` | Admin |
| GET | `/admin/pendentes` | Admin |
| GET | `/admin/solicitacao/{id}` | Admin |
| POST | `/admin/solicitacao/{id}/aprovar` | Admin |
| POST | `/admin/solicitacao/{id}/rejeitar` | Admin |
| GET | `/admin/historico` | Admin |
