# Self-hosted database (Postgres) — setup, migration & backups

The app can run on **Supabase** (managed) or a **self-hosted Postgres** container
(the `db` service in `docker-compose.yml`). It prefers `SUPABASE_URL`; when that's
blank it uses the local `DATABASE_URL`. So you cut over deliberately — deploying
the compose change alone does **not** switch you off Supabase.

## 1. Prerequisite

Add a strong password to the **root** `.env` (the Compose one, next to
`docker-compose.yml`):

```
POSTGRES_PASSWORD=<long-random-string>     # python3 -c "import secrets;print(secrets.token_urlsafe(24))"
```

## 2. Start Postgres (still on Supabase at this point)

```bash
cd ~/invoiceparsed
git pull
docker compose up -d db          # brings up Postgres; app still uses Supabase
docker compose ps                # db should be "healthy"
```

## 3. Migrate your data from Supabase → local Postgres

Use Supabase's **direct** connection string (Session mode, port **5432**), not the
pooler (6543) — `pg_dump` needs a session connection. Find it in the Supabase
dashboard → Project Settings → Database → Connection string (URI).

```bash
# Dump from Supabase and load into the local db, in one shot, inside the db container:
docker compose exec db sh -c \
  "pg_dump '<SUPABASE_DIRECT_URL>' --no-owner --no-privileges | psql -U invoiceparsed -d invoiceparsed"
```

Spot-check the data landed:

```bash
docker compose exec db psql -U invoiceparsed -d invoiceparsed -c \
  "select count(*) as users from users; select count(*) as extractions from extractions;"
```

## 4. Cut over

In **`backend/.env`**, blank the Supabase URL so the app uses the local Postgres:

```
SUPABASE_URL=
```

Then recreate the backend:

```bash
docker compose up -d --force-recreate backend
docker compose logs backend | tail   # should connect to db, no errors
```

Log in and confirm your account/plan/history are intact. Done — you're on the
self-hosted database.

## 5. Backups (important)

The `db-backup` service writes a daily gzipped dump to `./backups` (keeps the last
7). Verify:

```bash
docker compose logs db-backup | tail
ls -lh ~/invoiceparsed/backups
```

⚠️ A backup on the same disk won't survive disk failure. **Copy them off-box**
regularly — e.g. from your laptop:

```bash
scp 'root@<vps-ip>:~/invoiceparsed/backups/*.gz' ~/invoiceparsed-backups/
```
(Or sync to InterServer Storage / S3 on a cron.)

**Restore** from a dump if ever needed:

```bash
gunzip -c backups/invoiceparsed-YYYYmmdd-HHMMSS.sql.gz | \
  docker compose exec -T db psql -U invoiceparsed -d invoiceparsed
```

## Rollback to Supabase

Set `SUPABASE_URL=` back to your Supabase string in `backend/.env` and
`docker compose up -d --force-recreate backend`. (Data written while on local
Postgres won't be in Supabase unless you migrate it back.)

## Notes
- Postgres is **not** exposed to the internet (no published port) — only the
  backend reaches it as `db:5432`.
- Tuned for a 2 GB box (`shared_buffers=128MB`, `max_connections=50`). If you bump
  the VPS RAM later, raise these.
- New schema columns: the app calls `create_all()` (creates missing tables) but
  does not alter existing ones — apply `ALTER TABLE` manually for new columns, as
  with Supabase.
