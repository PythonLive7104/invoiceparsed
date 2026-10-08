# The database

InvoiceParsed ships with its **own Postgres**, running as the `db` service in
`docker-compose.yml`. There is no external database to sign up for and nothing
to configure — `docker compose up -d --build` brings up Postgres, the API, nginx,
Redis and a nightly backup together.

```
docker compose up -d --build
docker compose ps          # db should be "healthy"
```

The app reaches it over the compose network as `db:5432`. The backend's
`DATABASE_URL` is assembled in `docker-compose.yml` from the root `.env`:

```
postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
```

Setting it there (rather than in `backend/.env`) means the hostname can never
drift from the service name.

> **Driver note.** The URL names its driver explicitly (`postgresql+psycopg2://`).
> SQLAlchemy 2.1 changed the default DBAPI for a bare `postgresql://` from
> psycopg2 to psycopg v3, and `requirements.txt` installs `psycopg2-binary` — so
> an unpinned URL fails at startup with `No module named 'psycopg'`. `config.py`
> normalises any driver-less Postgres URL to psycopg2, so a plain
> `postgresql://…` you paste anywhere will work. A URL that names its own driver
> (`postgresql+psycopg://`, `+asyncpg`) is left as written.

## Before you deploy: set a password

Copy the root env template and set `POSTGRES_PASSWORD`:

```bash
cp .env.example .env
python3 -c "import secrets;print(secrets.token_urlsafe(24))"   # paste as POSTGRES_PASSWORD
```

Defaults exist (`invoiceparsed`/`invoiceparsed`) so a fresh clone starts without
configuration, but change it for anything real.

> Changing `POSTGRES_PASSWORD` **after** the volume has been initialised does not
> change the password inside Postgres — the credentials were baked in on first
> boot. To rotate it:
> ```bash
> docker compose exec db psql -U invoiceparsed -c "ALTER USER invoiceparsed PASSWORD 'new-password';"
> # then put the same value in the root .env and recreate the backend
> docker compose up -d --force-recreate backend
> ```

## Facts worth knowing

- **Not reachable from the internet.** The `db` service publishes no ports; only
  the other containers can connect. Nothing to firewall.
- **Data survives restarts.** It lives in the `pgdata` named volume, which
  outlives `docker compose down`. `docker compose down -v` **deletes it** —
  that's the one command to be careful with.
- **Resources.** Roughly 150 MB RAM, tuned for a 2 GB box
  (`shared_buffers=128MB`, `max_connections=50`). Raise them in
  `docker-compose.yml` if you give the VPS more.
- **Schema.** The app calls `create_all()` on boot, which creates *missing*
  tables but never alters existing ones. New columns need a manual
  `ALTER TABLE`; new tables appear on their own.

## Backups

The `db-backup` service writes a gzipped dump to `./backups` once a day and keeps
the last 7:

```bash
docker compose logs db-backup | tail
ls -lh backups/
```

Force one immediately:

```bash
docker compose exec db-backup sh -c \
  'pg_dump -h db | gzip > /backups/manual-$(date +%Y%m%d-%H%M%S).sql.gz'
```

⚠️ **Same-disk backups don't survive disk failure — copy them off-box:**

```bash
scp 'root@<vps-ip>:~/invoiceparsed/backups/*.gz' ~/invoiceparsed-backups/
```

### Restore

```bash
gunzip -c backups/invoiceparsed-YYYYmmdd-HHMMSS.sql.gz | \
  docker compose exec -T db psql -U invoiceparsed -d invoiceparsed
```

## Inspecting the database

```bash
docker compose exec db psql -U invoiceparsed -d invoiceparsed

# or one-off queries
docker compose exec db psql -U invoiceparsed -d invoiceparsed \
  -c "select count(*) from users; select count(*) from extractions;"
```

## Migrating in from a managed Postgres (Supabase etc.)

If you were previously on Supabase, move the data across once. Use Supabase's
**direct** connection string (Session mode, port **5432**) — the pooler (6543)
won't work with `pg_dump`. Find it under Project Settings → Database →
Connection string (URI).

```bash
# 1. Start just the database
docker compose up -d db
docker compose ps                      # wait for "healthy"

# 2. Copy the data in
docker compose exec db sh -c \
  "pg_dump '<SUPABASE_DIRECT_URL>' --no-owner --no-privileges | psql -U invoiceparsed -d invoiceparsed"

# 3. Verify
docker compose exec db psql -U invoiceparsed -d invoiceparsed \
  -c "select count(*) from users; select count(*) from extractions;"

# 4. Bring everything up on the local database
docker compose up -d --build
docker compose logs backend | tail     # connects to db, no errors
```

Then sign in and confirm your account, plan and history are intact. Remove any
`SUPABASE_URL` left in `backend/.env` so nothing points at the old database.

> `DATABASE_URL` takes precedence over `SUPABASE_URL`, and `docker-compose.yml`
> blanks `SUPABASE_URL` for the backend anyway, so a leftover value can't quietly
> win. The fallback exists only so an older install keeps running until migrated.

## Going back to a managed database

Set `SUPABASE_URL` (or any `DATABASE_URL`) in the backend's environment and
remove the `db` override. The simplest route is a small override file:

```yaml
# docker-compose.managed.yml
services:
  backend:
    environment:
      DATABASE_URL: postgresql://user:pass@your-host:5432/invoiceparsed
```

```bash
docker compose -f docker-compose.yml -f docker-compose.managed.yml up -d --force-recreate backend
```

Data written while on the local database stays in `pgdata` — migrate it out the
same way as above, with the hosts reversed, before cutting over.

## Running the API outside Docker

A host process can't resolve `db`, so `backend/.env`'s `DATABASE_URL` is for
host-local dev only. Either use SQLite (zero setup):

```env
DATABASE_URL=sqlite:///invoiceparsed.db
```

…or use the containerised Postgres over localhost. `docker-compose.dev.yml`
publishes its port for exactly this (bound to `127.0.0.1`, so it stays off the
network — don't apply that file on a public server):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

```env
# backend/.env
DATABASE_URL=postgresql://invoiceparsed:invoiceparsed@localhost:5432/invoiceparsed
```

The same published port lets you attach `psql` or a GUI client from your machine.
