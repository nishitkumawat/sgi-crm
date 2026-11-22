from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('SGIERP', '0023_merge_20261120_1130'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductionPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='production_plans_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Production Plan',
                'verbose_name_plural': 'Production Plans',
                'db_table': 'sgi_production_plan',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ProductionPlanItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('order', models.PositiveIntegerField(default=0)),
                ('completed_quantity', models.PositiveIntegerField(default=0)),
                ('plan', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='SGIERP.productionplan',
                )),
                ('machine', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='plan_items',
                    to='SGIERP.machine',
                )),
            ],
            options={
                'verbose_name': 'Production Plan Item',
                'verbose_name_plural': 'Production Plan Items',
                'db_table': 'sgi_production_plan_item',
                'ordering': ['order', 'id'],
            },
        ),
    ]
