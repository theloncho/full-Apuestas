# Integridad, Juego Responsable y Cumplimiento Normativo (Ley 31557)

Este documento detalla las decisiones arquitectónicas clave implementadas en TITANBET para garantizar la robustez financiera, promover el juego seguro y alinearse con el marco regulatorio peruano de apuestas deportivas a distancia (Ley N° 31557).

---

## 1. Garantía de Integridad Financiera

La arquitectura financiera de TITANBET fue diseñada bajo un principio de "cero confianza" (zero-trust) y contabilidad por partida doble, asegurando que los saldos nunca puedan ser alterados por condiciones de carrera o fallos del sistema.

### A. Contabilidad de Partida Doble (Double-Entry Ledger)
No existe un campo "saldo" estático modificable arbitrariamente. El saldo de un usuario es siempre la suma calculada de sus movimientos financieros (`LedgerEntry`). Cada vez que un usuario apuesta, el sistema registra una salida (debito) y bloquea los fondos; si gana, registra una entrada (crédito). Esto garantiza que el dinero nunca se "crea" o "destruye" sin un rastro contable estricto.

### B. Bloqueo Transaccional (Select-For-Update)
Para evitar los ataques de "doble gasto" (condiciones de carrera donde un usuario hace clic múltiples veces simultáneamente para apostar dinero que no tiene), el `WalletService` envuelve todas las operaciones en bloques `transaction.atomic()` de la base de datos y utiliza `select_for_update()`. Esto bloquea la fila del usuario a nivel de base de datos hasta que la transacción termina, garantizando consistencia absoluta incluso bajo alta concurrencia.

### C. Registro de Auditoría Inmutable (Hash Chaining)
Todas las acciones críticas (apuestas, depósitos, liquidaciones) se registran en la tabla `AuditLog`. Para prevenir la manipulación interna de la base de datos (por ejemplo, un administrador intentando borrar una apuesta perdedora), cada registro de auditoría calcula un hash criptográfico `SHA-256` utilizando sus propios datos combinados con el hash del registro anterior. Si alguien modifica directamente la base de datos, la cadena de hashes se rompe, revelando inmediatamente la manipulación.

---

## 2. Decisiones de Juego Responsable

TITANBET no solo busca la rentabilidad, sino la sostenibilidad a través de la protección al jugador. El módulo `apps.fraud` gestiona de manera proactiva los límites y comportamientos de riesgo.

*   **Límites Configurables (`GamblingLimit`):**
    Los usuarios pueden (y deben) establecer límites de depósito, límites de pérdidas y límites de tiempo de sesión (diarios, semanales o mensuales). El sistema intercepta las apuestas y los depósitos; si una acción viola el límite establecido, la transacción es rechazada automáticamente.
*   **Autoexclusión y "Time-Out":**
    Los jugadores que sientan que están perdiendo el control pueden solicitar un bloqueo temporal o permanente de su cuenta. Durante este período, el motor de autenticación impide el inicio de sesión y la colocación de nuevas apuestas.
*   **Monitoreo de Actividad Sospechosa (`SuspiciousActivity`):**
    El sistema rastrea patrones de riesgo, como aumentos drásticos en la frecuencia de apuestas (chasing losses) o múltiples intentos fallidos de depósito. Esto activa alertas tempranas para que el equipo de soporte intervenga.

---

## 3. Ley 31557: Cumplimiento y Autocrítica Honesta

La Ley N° 31557 (y su modificatoria Ley N° 31806) regula la explotación de los juegos a distancia y apuestas deportivas a distancia en el Perú. A continuación, un análisis honesto de lo que cubre nuestra implementación y lo que falta.

### ¿Qué requisitos SÍ quedan cubiertos?
1.  **Protección a Menores y KYC Básico:** La ley prohíbe el acceso a menores de edad. Nuestro modelo de usuario requiere verificación de identidad y validación de mayoría de edad antes de permitir depósitos reales.
2.  **Trazabilidad y Prevención de Lavado de Activos (PLAFT):** Gracias al `AuditLog` inmutable y a los límites de depósito/retiro (reportando actividades sospechosas si un usuario mueve grandes sumas sin justificación deportiva), cumplimos con los estándares básicos de reporte exigidos por la UIF-Perú.
3.  **Políticas de Juego Responsable:** La ley exige mecanismos claros para que el jugador pueda limitar sus pérdidas y autoexcluirse. Nuestro sistema cumple a cabalidad con la infraestructura técnica para aplicar estos bloqueos al instante.
4.  **No repudio:** El enlazado criptográfico asegura que la empresa no pueda repudiar ni alterar retrospectivamente apuestas válidas ganadas por los usuarios.

### ¿Qué requisitos NO quedan cubiertos aún? (Autocrítica y Deuda Técnica)
Siendo este un MVP/Proyecto académico funcional, existen lagunas regulatorias que requerirían desarrollo adicional para operar legalmente en el mercado abierto:

1.  **Homologación Técnica y Servidores Mincetur:** 
    *Faltante:* La ley exige que la plataforma esté conectada e integrada mediante APIs directamente con los servidores del MINCETUR y la SUNAT para control en tiempo real. Actualmente no tenemos desarrollados estos webhooks gubernamentales.
2.  **Validación Biométrica / RENIEC:** 
    *Faltante:* Aunque tenemos un campo de DNI y un estado de cuenta "Verificado", la verificación real exige interconexión con los servicios de RENIEC o un proveedor de KYC como Mati/Sumsub. Actualmente la verificación es un simple *flag* que cambia el administrador.
3.  **Retención de Impuestos (ISC):**
    *Faltante:* La ley establece el cobro del Impuesto Selectivo al Consumo (ISC) sobre la tasa de retorno de los jugadores. Nuestro `LiquidationService` actualmente paga el 100% del `payout` bruto (restando solo el margen implícito en la cuota). Carecemos del motor fiscal que retenga el porcentaje obligatorio por ley antes de acreditarlo en la billetera del usuario.
4.  **Pasarelas de Pago Reguladas:**
    *Faltante:* Las transacciones operan usando "fichas" o "tokens" de prueba. Para cumplir, se debe integrar pasarelas de pago peruanas reales (Niubiz, Culqi, PagoEfectivo) en cuentas fideicomisadas, asegurando que los fondos de los jugadores no se mezclen con el patrimonio de la empresa.

### Conclusión
TITANBET posee una base transaccional y de auditoría de grado empresarial que supera a muchos operadores pequeños. Sin embargo, el "último kilómetro" normativo requeriría construir los puentes de comunicación directa con las instituciones del Estado peruano (SUNAT/MINCETUR) y proveedores de pagos autorizados.
