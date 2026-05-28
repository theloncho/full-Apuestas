# ADR 0008: Auditoría Inmutable (Append-only)

**Fecha:** 2026-05-27
**Estado:** Aceptado

## Contexto
El historial de transacciones financieras y de apuestas debe ser inmutable y auditable matemáticamente.

## Opciones Consideradas
1. Confiar en la lógica de la aplicación para no hacer UPDATE o DELETE.
2. Usar un trigger de base de datos junto con encadenamiento criptográfico.

## Decisión
Se implementará la **Opción 2**. `AuditLog` utilizará un `chain_hash` basado en SHA-256 (`hash_n = SHA256(hash_{n-1} + payload_n)`). Además, se añadirán reglas `RULE` en PostgreSQL que interceptarán y anularán silenciosamente (`DO INSTEAD NOTHING`) cualquier comando `UPDATE` o `DELETE` sobre la tabla.

## Consecuencias
- Imposibilidad técnica de alterar registros históricos, ni siquiera mediante comandos SQL directos o acceso de administrador.
- El rendimiento al insertar se ve ligeramente afectado por el cálculo del hash, pero garantiza seguridad total.
