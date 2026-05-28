# Generated manually — actualiza SuspiciousActivity al modelo completo

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fraud', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Renombrar campos viejos → nuevos
        migrations.RenameField(
            model_name='suspiciousactivity',
            old_name='rule_type',
            new_name='activity_type',
        ),
        migrations.RenameField(
            model_name='suspiciousactivity',
            old_name='description',
            new_name='reason',
        ),
        # Agregar severity
        migrations.AddField(
            model_name='suspiciousactivity',
            name='severity',
            field=models.CharField(
                choices=[
                    ('low', 'Baja'),
                    ('medium', 'Media'),
                    ('high', 'Alta'),
                    ('critical', 'Crítica'),
                ],
                default='low',
                max_length=20,
            ),
        ),
        # Agregar status (reemplaza reviewed BooleanField)
        migrations.AddField(
            model_name='suspiciousactivity',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pendiente'),
                    ('reviewed', 'Revisada'),
                    ('dismissed', 'Descartada'),
                    ('confirmed', 'Confirmada'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        # Agregar reviewed_at (ya existe en 0001 como reviewed_at)
        # Eliminar campo reviewed (BooleanField viejo)
        migrations.RemoveField(
            model_name='suspiciousactivity',
            name='reviewed',
        ),
        # Actualizar activity_type choices para incluir opposite_bets_hedging
        migrations.AlterField(
            model_name='suspiciousactivity',
            name='activity_type',
            field=models.CharField(
                choices=[
                    ('same_ip_multi_account', 'Misma IP, múltiples cuentas'),
                    ('identical_bet_pattern', 'Patrón de apuestas idénticas'),
                    ('deposit_cashout', 'Depósito inmediato + cash-out'),
                    ('bonus_abuse', 'Abuso de bono'),
                    ('opposite_bets_hedging', 'Apuestas opuestas o cobertura'),
                ],
                max_length=50,
            ),
        ),
    ]
