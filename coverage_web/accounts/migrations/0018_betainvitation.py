from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0017_parseable_target_cycles")]

    operations = [
        migrations.CreateModel(
            name="BetaInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("email_fingerprint", models.CharField(editable=False, max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("redeemed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="beta_invitations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "beta_invitations", "ordering": ("created_at", "pk")},
        ),
    ]
