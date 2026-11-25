"""Guards on the migration files themselves.

Alembic's autogenerate emits unnamed constraints, and SQLite's batch mode -
which every ALTER on SQLite goes through - rejects them, because it rebuilds
the table and has to name every constraint it recreates. The result is a
migration that looks fine in review and fails the deploy. This has happened
twice; a test is cheaper than remembering.
"""
import pathlib
import re

MIGRATIONS = sorted(
    pathlib.Path(__file__).resolve().parents[1].joinpath("migrations/versions").glob("*.py")
)


def test_there_are_migrations_to_check():
    assert MIGRATIONS, "no migration files found - has the path moved?"


def test_no_migration_creates_an_unnamed_constraint():
    offenders = []
    for path in MIGRATIONS:
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(create_foreign_key|create_unique_constraint)\(\s*None", source):
            offenders.append(f"{path.name}: {match.group(1)}(None, ...)")
    assert not offenders, (
        "Unnamed constraints fail on SQLite batch mode. Give each one an "
        "explicit name:\n  " + "\n  ".join(offenders)
    )


def test_no_migration_drops_an_unnamed_constraint():
    offenders = [
        path.name for path in MIGRATIONS
        if re.search(r"drop_constraint\(\s*None", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "drop_constraint(None) cannot work - the downgrade will fail: "
        + ", ".join(offenders)
    )


def test_no_migration_still_carries_the_autogenerate_warning():
    """Alembic writes a 'this directive will fail as rendered' comment when it
    cannot name something. If it survived review, the migration is broken.

    Matched on alembic's own comment rather than the phrase alone, so a
    docstring that explains the hazard — which is worth writing — does not
    read as the hazard itself.
    """
    marker = re.compile(
        r"^\s*#\s*WARNING: constraint name is None", re.M
    )
    offenders = [
        path.name for path in MIGRATIONS
        if marker.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, ", ".join(offenders)


def test_every_migration_declares_its_place_in_the_chain():
    for path in MIGRATIONS:
        source = path.read_text(encoding="utf-8")
        assert re.search(r"^revision = ", source, re.M), path.name
        assert re.search(r"^down_revision = ", source, re.M), path.name


def test_the_chain_has_exactly_one_root_and_no_forks():
    """Two migrations sharing a down_revision is a branch, and `db upgrade`
    refuses to run with multiple heads."""
    revisions, parents = {}, []
    for path in MIGRATIONS:
        source = path.read_text(encoding="utf-8")
        rev = re.search(r"^revision = ['\"]([^'\"]+)", source, re.M).group(1)
        down = re.search(r"^down_revision = (.+)$", source, re.M).group(1).strip()
        revisions[rev] = path.name
        parents.append(None if down.startswith("None") else down.strip("'\""))

    roots = [p for p in parents if p is None]
    assert len(roots) == 1, f"expected exactly one root migration, found {len(roots)}"

    named = [p for p in parents if p is not None]
    duplicates = {p for p in named if named.count(p) > 1}
    assert not duplicates, f"branched history - these have two children: {duplicates}"


def test_no_migration_adds_a_not_null_column_without_a_default():
    """`ALTER TABLE ... ADD COLUMN ... NOT NULL` with no default fails on
    PostgreSQL the moment the table has a single row.

    It passes locally against an empty test database and on SQLite, then takes
    the deploy down on a server with real data — the same shape of failure as
    the unnamed-constraint bug above, and just as invisible in review.
    A `server_default` backfills the existing rows and makes it safe.

    Only ADD COLUMN is checked. A column declared NOT NULL inside a
    `create_table` is fine: the table is new, so it has no rows to violate it.
    """
    offenders = []
    # add_column(...) up to its closing paren, across lines.
    pattern = re.compile(r"add_column\(\s*sa\.Column\((.*?)\)\s*\)", re.S)
    for path in MIGRATIONS:
        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            body = match.group(1)
            if "nullable=False" not in body:
                continue
            if "server_default" in body:
                continue
            name = re.search(r"""['"]([a-z_]+)['"]""", body)
            offenders.append(f"{path.name}: {name.group(1) if name else body[:40]}")
    assert not offenders, (
        "A NOT NULL column added to an existing table needs a server_default, "
        "or the migration fails on any database that already has rows:\n  "
        + "\n  ".join(offenders)
    )
