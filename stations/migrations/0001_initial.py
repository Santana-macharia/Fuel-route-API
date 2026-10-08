from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Station",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opis_id", models.PositiveIntegerField(unique=True)),
                ("name", models.CharField(max_length=200)),
                ("address", models.CharField(max_length=200)),
                ("city", models.CharField(max_length=100)),
                ("state", models.CharField(max_length=2)),
                ("price", models.DecimalField(decimal_places=6, max_digits=9)),
                ("lat", models.FloatField()),
                ("lng", models.FloatField()),
            ],
        ),
    ]
