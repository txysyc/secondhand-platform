# 由 Django 6.0.4 于 2026-05-23 10:58 生成

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_alter_order_payment_deadline'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='received_at',
        ),
        migrations.AddField(
            model_name='order',
            name='completed_at',
            field=models.DateTimeField(null=True, verbose_name='签收时间'),
        ),
        migrations.AddField(
            model_name='order',
            name='logistics_signed_due_at',
            field=models.DateTimeField(null=True, verbose_name='模拟物流到达时间'),
        ),
        migrations.AddField(
            model_name='order',
            name='signed_at',
            field=models.DateTimeField(null=True, verbose_name='签收时间'),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('pending_payment', '待支付'), ('cancelled', '已取消'), ('awaiting_shipment', '待发货'), ('awaiting_receipt', '待收货'), ('signed', '已签收'), ('completed', '已完成')], default='pending_payment', max_length=20, verbose_name='订单状态'),
        ),
    ]
