# 由 Django 6.0.4 于 2026-05-23 12:07 生成

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_remove_order_received_at_order_completed_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='shipped_at',
            field=models.DateTimeField(null=True, verbose_name='卖家确认发货时间'),
        ),
    ]
