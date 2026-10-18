from django.db import migrations

SYNCABLE_TABLES = (
    "people_department",
    "people_employee",
    "people_credential",
    "access_zone",
    "access_readerprofile",
    "access_door",
    "access_reader",
)


def _sql() -> str:
    statements = [
        "CREATE SEQUENCE IF NOT EXISTS sync_version_seq AS bigint;",
        """
        CREATE OR REPLACE FUNCTION assign_sync_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.version := nextval('sync_version_seq');
            RETURN NEW;
        END;
        $$;
        """,
    ]
    for table in SYNCABLE_TABLES:
        trigger = f"{table}_sync_version"
        statements.append(f"DROP TRIGGER IF EXISTS {trigger} ON {table};")
        statements.append(
            f"""
            CREATE TRIGGER {trigger}
            BEFORE INSERT OR UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION assign_sync_version();
            """
        )
    return "\n".join(statements)


def _reverse_sql() -> str:
    statements = [
        f"DROP TRIGGER IF EXISTS {table}_sync_version ON {table};" for table in SYNCABLE_TABLES
    ]
    statements.append("DROP FUNCTION IF EXISTS assign_sync_version();")
    statements.append("DROP SEQUENCE IF EXISTS sync_version_seq;")
    return "\n".join(statements)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("people", "0001_initial"),
        ("access", "0002_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=_sql(), reverse_sql=_reverse_sql()),
    ]
