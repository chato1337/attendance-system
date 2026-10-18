import django.db.models.deletion
import django.db.models.manager
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0003_accessnode_agent_version_and_more"),
        ("sync", "0002_initial"),
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EnrollmentRead",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("raw", models.TextField(blank=True)),
                ("payload", models.TextField(blank=True)),
                ("credential_type", models.CharField(blank=True, max_length=20)),
                ("error", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "command",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="enrollment_reads",
                        to="sync.edgecommand",
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enrollment_reads",
                        to="access.accessnode",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(app_label)s_%(class)s_set",
                        to="tenants.organization",
                    ),
                ),
                (
                    "reader",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="enrollment_reads",
                        to="access.reader",
                    ),
                ),
            ],
            options={
                "verbose_name": "lectura de enrolamiento",
                "verbose_name_plural": "lecturas de enrolamiento",
                "ordering": ["-created_at"],
                "base_manager_name": "all_objects",
                "default_manager_name": "objects",
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("all_objects", django.db.models.manager.Manager()),
            ],
        ),
    ]
