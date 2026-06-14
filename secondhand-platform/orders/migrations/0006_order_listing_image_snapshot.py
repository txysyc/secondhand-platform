from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_alter_order_shipped_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="listing_image_snapshot",
            field=models.URLField(
                blank=True,
                null=True,
                verbose_name="商品首图快照",
            ),
        ),
    ]
