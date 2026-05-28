"""
Auditoría inmutable con encadenamiento por hash.
hash_n = SHA256(hash_{n-1} + payload_n)

NUNCA hacer UPDATE ni DELETE en esta tabla.
Se protege a nivel DB con reglas PostgreSQL (ver migración).
"""
import hashlib
import json
import uuid
from django.db import models, transaction


class AuditLog(models.Model):
    """
    Tabla append-only con encadenamiento por hash SHA-256.
    Registra: apuestas, movimientos de wallet, cambios de odds,
    liquidaciones, cash-outs, auto-exclusiones, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    user = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='audit_logs',
    )
    hash = models.CharField(max_length=64)           # SHA256 del payload
    previous_hash = models.CharField(max_length=64)  # hash del registro anterior
    chain_hash = models.CharField(max_length=64)     # SHA256(previous_hash + payload)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Registros de auditoría'

    @classmethod
    @transaction.atomic
    def log(cls, event_type: str, payload: dict, user=None) -> 'AuditLog':
        """
        Registra un evento en la cadena de auditoría.
        Cada registro se encadena al anterior via hash.
        """
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()

        # Obtener el último hash de la cadena
        last = cls.objects.order_by('-created_at').first()
        previous_hash = last.chain_hash if last else '0' * 64

        chain_hash = hashlib.sha256(
            (previous_hash + payload_str).encode()
        ).hexdigest()

        return cls.objects.create(
            event_type=event_type,
            payload=payload,
            user=user,
            hash=payload_hash,
            previous_hash=previous_hash,
            chain_hash=chain_hash,
        )

    @classmethod
    def verify_chain_integrity(cls) -> dict:
        """
        Recorre toda la cadena y verifica cada hash.
        Retorna {'valid': True} o {'valid': False, 'broken_at': id}.
        """
        entries = cls.objects.order_by('created_at').all()
        previous_hash = '0' * 64

        for entry in entries:
            payload_str = json.dumps(entry.payload, sort_keys=True, default=str)
            expected_chain = hashlib.sha256(
                (previous_hash + payload_str).encode()
            ).hexdigest()

            if entry.chain_hash != expected_chain:
                return {
                    'valid': False,
                    'broken_at': str(entry.id),
                    'created_at': entry.created_at.isoformat(),
                    'event_type': entry.event_type,
                }
            previous_hash = entry.chain_hash

        return {'valid': True, 'total_entries': entries.count()}

    def __str__(self):
        return f"[{self.event_type}] {self.created_at}"
