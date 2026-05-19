from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('poll', '0011_alter_poll_config_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='poll',
            name='config_number',
            field=models.IntegerField(
                blank=True,
                choices=[
                    (1, 'Cau hinh 1: Phieu gach ten + ResNet18 crossed'),
                    (2, 'Cau hinh 2: Theo thu tu + ResNet18-X'),
                    (3, 'Cau hinh 3: VietNameOCR + ResNet18-X'),
                ],
                help_text='Cấu hình AI model đã sử dụng để kiểm phiếu',
                null=True,
            ),
        ),
    ]
