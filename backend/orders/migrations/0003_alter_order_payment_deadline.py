# 由 Django 6.0.4 于 2026-05-21 11:35 生成

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_rename_buyer_diaplay_name_order_buyer_display_name_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='payment_deadline',
            field=models.DateTimeField(verbose_name='截止时间'),
        ),
    ]
