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
    cannot name something. If it survived review, the migration is broken."""
    offenders = [
        path.name for path in MIGRATIONS
        if "will fail as" in path.read_text(encoding="utf-8")
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
