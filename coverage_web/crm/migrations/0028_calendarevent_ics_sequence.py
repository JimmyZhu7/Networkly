from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0027_contact_region_source_reply'),
    ]

    operations = [
        migrations.AddField(
            model_name='calendarevent',
            name='ics_sequence',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
