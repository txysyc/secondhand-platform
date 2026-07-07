# 由 Django 6.0.4 于 2026-05-20 12:44 生成

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='buyer_diaplay_name',
            new_name='buyer_display_name',
        ),
        migrations.RenameIndex(
            model_name='order',
            new_name='orders_orde_buyer_i_4389c9_idx',
            old_name='orders_orde_buyer_i_4a5ff4_idx',
        ),
        migrations.RenameIndex(
            model_name='order',
            new_name='orders_orde_seller__c90b9c_idx',
            old_name='orders_orde_seller__912a3b_idx',
        ),
        migrations.RenameIndex(
            model_name='order',
            new_name='orders_orde_listing_84df4c_idx',
            old_name='orders_orde_listing_134a79_idx',
        ),
        migrations.RenameIndex(
            model_name='order',
            new_name='orders_orde_status_ae3a03_idx',
            old_name='orders_orde_status_e5c983_idx',
        ),
        migrations.AlterField(
            model_name='order',
            name='cancelled_at',
            field=models.DateTimeField(null=True, verbose_name='取消时间'),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('pending_payment', '待支付'), ('cancelled', '已取消'), ('awaiting_shipment', '待发货'), ('awaiting_receipt', '待收货'), ('completed', '已完成')], default='pending_payment', max_length=20, verbose_name='订单状态'),
        ),
    ]
