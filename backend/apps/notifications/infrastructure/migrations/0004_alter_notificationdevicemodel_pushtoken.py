from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_phase15_platform'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notificationdevicemodel',
            name='pushToken',
            field=models.CharField(max_length=2048),
        ),
    ]
