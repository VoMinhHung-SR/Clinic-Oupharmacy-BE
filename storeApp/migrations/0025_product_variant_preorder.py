# Generated manually for preorder MVP

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0024_consultation_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="allow_preorder",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Cho phép đặt trước khi hết hàng (không trừ kho lúc checkout)",
            ),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="preorder_eta_days",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Số ngày dự kiến có hàng lại (hiển thị FE)",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Chờ xử lý"),
                    ("PREORDER_PENDING_STOCK", "Đặt trước — chờ hàng"),
                    ("CONFIRMED", "Đã xác nhận"),
                    ("SHIPPING", "Đang giao hàng"),
                    ("DELIVERED", "Đã giao"),
                    ("CANCELLED", "Đã hủy"),
                ],
                db_column="status",
                default="PENDING",
                max_length=20,
            ),
        ),
    ]
