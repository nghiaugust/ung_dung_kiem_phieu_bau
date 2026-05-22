from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("poll", "0010_poll_is_checking_started"),
    ]

    operations = [
        migrations.AlterField(
            model_name="poll",
            name="config_number",
            field=models.IntegerField(
                blank=True,
                choices=[
                    (1, "Cấu hình 1: Chỉ YOLO"),
                    (2, "Cấu hình 2: VietNameOCR + YOLO"),
                ],
                help_text="Cấu hình AI model đã sử dụng để kiểm phiếu",
                null=True,
            ),
        ),
    ]
