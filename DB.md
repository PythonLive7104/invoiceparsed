# Self-hosting the database (optional)

**By default the app uses Supabase** (managed, zero RAM on your box). You only
need this if you want to drop Supabase later — e.g. to avoid its paid tier as you
grow. Self-hosted Postgres runs as the `db` service in `docker-compose.selfhost.yml`
and costs ~150 MB RAM. It's a full PostgreSQL 16 — functionally identical to
Supabase; only backups become your responsibility (handled below).

The app prefers `SUPABASE_URL` over `DATABASE_URL`, and the override blanks
`SUPABASE_URL`, so the switch is deliberate — nothing changes until you opt in.

## 1. Prerequisite

Add a strong password to the **root** `.env` (next to `docker-compose.yml`):

```
POSTGRES_PASSWORD=<long-random>     # python3 -c "import secrets;print(secrets.token_urlsafe(24))"
```

## 2. Start only Postgres (app stays on Supabase)

```bash
cd ~/invoiceparsed
git pull
docker compose -f docker-compose.yml -f docker-compose.selfhost.yml up -d db
docker compose -f docker-compose.yml -f docker-compose.selfhost.yml ps   # db "healthy"
```

## 3. Migrate your data from Supabase → local Postgres

Use Supabase's **direct** connection string (Session mode, port **5432**) — find it
in Supabase → Project Settings → Database → Connection string (URI). The pooler
(6543) won't work for `pg_dump`.

```bash
docker compose -f docker-compose.yml -f docker-compose.selfhost.yml exec db sh -c \
  "pg_dump '<SUPABASE_DIRECT_URL>' --no-owner --no-privileges | psql -U invoiceparsed -d invoiceparsed"
```

Verify:

```bash
docker compose -f docker-compose.yml -f docker-compose.selfhost.yml exec db \
  psql -U invoiceparsed -d invoiceparsed -c "select count(*) from users; select count(*) from extractions;"
```

## 4. Cut over

Persist the file list in the root `.env` so every command uses both files:

```
COMPOSE_FILE=docker-compose.yml:docker-compose.selfhost.yml
# (if you also use TLS: docker-compose.yml:docker-compose.prod.yml:docker-compose.selfhost.yml)
```

Then bring everything up — the backend recreates pointing at the local DB:

```bash
docker compose up -d --build
docker compose logs backend | tail    # connects to db, no errors
```

Log in and confirm your account/plan/history are intact. Done.

## 5. Backups (important)

`db-backup` writes a daily gzip to `./backups` (keeps the last 7):

```bash
docker compose logs db-backup | tail
ls -lh ~/invoiceparsed/backups
```

⚠️ Same-disk backups won't survive disk failure — **copy them off-box**, e.g.:

```bash
scp 'root@<vps-ip>:~/invoiceparsed/backups/*.gz' ~/invoiceparsed-backups/
```

**Restore:**

```bash
gunzip -c backups/invoiceparsed-YYYYmmdd-HHMMSS.sql.gz | \
  docker compose exec -T db psql -U invoiceparsed -d invoiceparsed
```

## Rollback to Supabase

Remove `docker-compose.selfhost.yml` from `COMPOSE_FILE` and
`docker compose up -d --force-recreate backend` (your `backend/.env` SUPABASE_URL
is used again). Data written while on local Postgres stays only in the local DB.

## Notes
- Postgres is **not** exposed to the internet (no published port).
- Tuned for 2 GB (`shared_buffers=128MB`, `max_connections=50`). Raise if you add RAM.
- New schema columns: the app `create_all()`s missing tables but doesn't alter
  existing ones — apply `ALTER TABLE` manually (same as with Supabase).
