from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('poll', '0010_poll_is_checking_started'),
    ]

    operations = [
        migrations.AlterField(
            model_name='poll',
            name='config_number',
            field=models.IntegerField(
                blank=True,
                choices=[
                    (1, 'Cau hinh 1: VietNameOCR + YOLO-X'),
                    (2, 'Cau hinh 2: Theo thu tu + YOLO-X'),
                    (3, 'Cau hinh 3: Phieu gach ten + ResNet18 crossed'),
                ],
                help_text='Cau hinh AI model da su dung de kiem phieu',
                null=True,
            ),
        ),
    ]
