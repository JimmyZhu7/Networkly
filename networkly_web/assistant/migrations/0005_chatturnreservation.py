import uuid

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0004_dailybrief_contact_ids"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatTurnReservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("conversation_key", models.PositiveBigIntegerField()),
                ("cost", models.PositiveIntegerField()),
                ("model", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("settled", "Settled"), ("refunded", "Refunded")], default="pending", max_length=16)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("reason", models.CharField(blank=True, default="", max_length=100)),
                ("conversation", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reservations", to="assistant.chatconversation")),
                ("reply", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="credit_reservations", to="assistant.chatmessage")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assistant_reservations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "assistant_turn_reservations",
                "abstract": False,
                "base_manager_name": "all_objects",
                "default_manager_name": "all_objects",
                "indexes": [models.Index(fields=["status", "created"], name="as_turn_pending_created")],
            },
            managers=[("all_objects", django.db.models.manager.Manager())],
        ),
    ]
