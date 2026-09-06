from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("billing", "0009_alter_creditledger_kind")]

    operations = [
        migrations.AddField(
            model_name="processedstripeevent",
            name="stripe_checkout_id",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
