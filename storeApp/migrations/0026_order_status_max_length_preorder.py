# Generated manually — Order.status max_length must fit PREORDER_PENDING_STOCK (22)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storeApp", "0025_product_variant_preorder"),
    ]

    operations = [
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
                max_length=32,
            ),
        ),
    ]
