# Arquitectura de Integridad, Juego Responsable y Cumplimiento Normativo (Ley N° 31557)

Este documento detalla las decisiones arquitectónicas, financieras y operativas implementadas en la plataforma educativa **TITANBET**. El objetivo de este análisis es demostrar cómo el diseño del sistema garantiza la robustez y seguridad de los fondos virtuales, promueve prácticas de juego responsable y se alinea con el marco regulatorio peruano aplicable a la explotación de apuestas deportivas a distancia (Ley N° 31557 y su modificatoria Ley N° 31806, reglamentadas por el DS N° 005-2023-MINCETUR).

---

## 1. Garantía de Integridad Financiera

En la industria de las apuestas, la integridad de los fondos y saldos es el pilar más crítico. La arquitectura de TITANBET fue diseñada bajo un principio de "cero confianza" (zero-trust) a nivel de base de datos, asegurando que los saldos nunca puedan ser alterados por condiciones de carrera, errores de concurrencia o manipulación directa.

### A. Contabilidad de Partida Doble (Double-Entry Ledger)
A diferencia de sistemas básicos que almacenan el saldo de un usuario en un campo estático (ej. `user.balance`), TITANBET utiliza un sistema de **contabilidad inmutable de partida doble**. El saldo de un usuario es siempre un campo derivado; es la suma matemática de todos sus movimientos financieros históricos (`LedgerEntry`).
*   **Créditos y Débitos:** Cada vez que un usuario apuesta, el sistema registra una salida (débito). Si el usuario gana, el motor de liquidación (`LiquidationService`) registra una entrada (crédito) equivalente al pago (`payout`).
*   **Ventaja:** Esto garantiza que el dinero nunca se "crea" o "destruye" sin un rastro contable estricto, permitiendo auditorías forenses precisas en cualquier momento.

### B. Bloqueo Transaccional y Concurrencia (Select-For-Update)
El principal riesgo en plataformas financieras web es el "doble gasto" (condiciones de carrera donde un usuario envía múltiples solicitudes en milisegundos para apostar fondos que no posee). 
Para mitigar esto, el `WalletService` envuelve todas las operaciones críticas en bloques de transacciones atómicas (`transaction.atomic()`) y utiliza bloqueos a nivel de fila (`select_for_update()`). Cuando un usuario inicia una apuesta, su registro de billetera se bloquea exclusivamente; ninguna otra solicitud concurrente puede leer o modificar el saldo hasta que la transacción principal se confirme (commit) o revierta (rollback).

### C. Registro de Auditoría Inmutable (Criptografía Hash Chaining)
Para prevenir la manipulación interna de la base de datos (por ejemplo, un empleado o un ciberdelincuente alterando directamente el estado de una apuesta perdedora en la base de datos), TITANBET implementa un mecanismo de encadenamiento de hashes inspirado en la tecnología blockchain.
Todas las acciones críticas se guardan en la tabla `AuditLog`. Cada nuevo registro calcula un hash `SHA-256` basado en sus datos internos combinados con el hash del registro inmediatamente anterior. Si algún dato histórico es modificado directamente vía SQL, la validación en cascada de los hashes fallará, exponiendo inmediatamente la manipulación de la información.

---

## 2. Decisiones y Mecanismos de Juego Responsable

La plataforma no solo se centra en la operación transaccional, sino que incorpora de forma nativa la protección al jugador, entendiendo que la ludopatía es un riesgo de salud pública. A través del módulo de prevención (`apps.fraud`), se tomaron las siguientes decisiones:

### A. Controles Activos del Jugador (Límites Configurables)
Se provee una interfaz donde los usuarios pueden y son incentivados a establecer barreras financieras y temporales (`GamblingLimit`):
*   **Límites de Depósito:** Restricciones sobre la cantidad máxima de fondos que pueden recargar diariamente, semanalmente o mensualmente.
*   **Límites de Apuestas/Pérdidas:** Restricción sobre el volumen de apuestas permitidas en un lapso específico.
Cada vez que el usuario intenta colocar una apuesta o recargar su cuenta, el sistema verifica en tiempo real su historial reciente contra los límites configurados. Si la transacción excede el umbral, es rechazada con un mensaje educativo sobre juego responsable.

### B. Autoexclusión y Suspensión Temporal (Time-Out)
El usuario tiene el derecho irrenunciable a pausar su actividad. El sistema permite la activación de bloqueos de cuenta (desde 24 horas hasta exclusiones permanentes). Una vez activado, el motor de autenticación expulsa la sesión activa y prohíbe el ingreso hasta que el plazo finalice. Durante este período, el sistema también suprime el envío de correos o notificaciones promocionales.

### C. Monitoreo Pasivo y Alertas de Riesgo
El sistema cuenta con un modelo de detección (`SuspiciousActivity`) que rastrea patrones anómalos. Comportamientos como *chasing losses* (intentar recuperar pérdidas aumentando drásticamente el tamaño de la apuesta tras perder repetidamente) o realizar depósitos de madrugada de forma compulsiva, generan alertas preventivas en el panel administrativo para posible intervención del área de soporte al cliente.

---

## 3. Cumplimiento de la Ley N° 31557 y DS 005-2023-MINCETUR

A continuación, se presenta un análisis exhaustivo y honesto sobre el nivel de cumplimiento normativo de la plataforma respecto a las exigencias peruanas para apuestas deportivas a distancia.

### 3.1. Requisitos SÍ Cubiertos por el Diseño Actual
1.  **Políticas de Juego Responsable y Autoexclusión (Art. 31 y 32 del Reglamento):** La plataforma cumple cabalmente con proporcionar a los jugadores las herramientas de limitación de depósitos y el registro voluntario de autoexclusión.
2.  **Protección a Menores y Restricción de Acceso (Art. 29):** La estructura del perfil de usuario y registro requiere obligatoriamente confirmación de mayoría de edad. La lógica de depósito bloquea cuentas que no cuenten con verificación del Documento Nacional de Identidad (DNI).
3.  **Trazabilidad Financiera e Inmutabilidad (PLAFT):** El sistema de contabilidad de partida doble y el `AuditLog` encriptado satisfacen las exigencias preliminares de conservación de datos y permiten generar los reportes de Operaciones Sospechosas (ROS) requeridos por la Unidad de Inteligencia Financiera (UIF-Perú) ante la Ley N° 27693 de prevención de lavado de activos.
4.  **Uso de Cuentas Individuales:** La base de datos garantiza que cada jugador posea una cuenta de usuario individual e intransferible, en la que se registran todas las apuestas, pagos y cobranzas.

### 3.2. Requisitos NO Cubiertos (Autocrítica y Deuda Técnica Regulatoria)
Al tratarse de una plataforma desarrollada con fines educativos y de demostración, existen lagunas técnicas y operativas que impedirían su lanzamiento comercial sin desarrollo adicional. Las principales carencias son:

1.  **Homologación Técnica y Certificación Internacional (GLI-19/GLI-33):**
    *   *Deuda:* La ley exige que el software y la infraestructura tecnológica estén certificados por un laboratorio homologado por el MINCETUR (como GLI o BMM Testlabs). El sistema actual no cuenta con esta certificación de generadores de números aleatorios (RNG) ni auditoría de seguridad ISO/IEC 27001 para sus servidores físicos.
2.  **Integración Directa con Sistemas del MINCETUR y SUNAT (Art. 42 y 46):**
    *   *Deuda:* Todo operador autorizado debe conectar sus servidores en tiempo real (mediante Webhooks o APIs dedicadas) con el centro de datos del MINCETUR y de la Superintendencia Nacional de Aduanas y de Administración Tributaria (SUNAT) para control, fiscalización e impuestos. Nuestra arquitectura actual es un silo aislado.
3.  **Retención Fiscal Automatizada (Impuesto Selectivo al Consumo - ISC):**
    *   *Deuda:* El marco normativo peruano prevé el cobro de un porcentaje tributario a nivel de usuario y empresa. Nuestro `LiquidationService` actualmente transfiere el 100% de la cuota (payout) de una apuesta ganada. Carecemos del motor contable fiscal necesario para calcular y retener porcentajes impositivos en nombre del fisco antes de acreditar fondos.
4.  **Idempotencia en Pasarelas de Pago (Prevención de Doble Cobro):**
    *   *Deuda:* Actualmente, si un usuario realiza una recarga y pierde la conexión a internet antes de recibir respuesta, el navegador podría reenviar la petición POST al actualizar la página. Como no contamos con llaves de idempotencia (`Idempotency-Key`) en el diseño del formulario de depósito, esto podría resultar en un doble abono involuntario. Una integración financiera real exigiría tokens únicos por transacción (ej. UUIDv4 en el frontend) para que el backend detecte y bloquee envíos duplicados de la misma operación.
5.  **Validación Biométrica Estricta con RENIEC:**
    *   *Deuda:* Si bien pedimos el DNI, la validación actual es una verificación administrativa básica. Para cumplir rigurosamente, se requiere integración mediante API con RENIEC o servicios de KYC avanzados (ej. Mati, Sumsub) que validen identidad vía biometría facial y corroboración de listas de prevención (PEP - Personas Expuestas Políticamente).
6.  **Pasarelas de Pago Autorizadas y Fideicomisos:**
    *   *Deuda:* Actualmente operamos con saldos virtuales educativos. Para operar con moneda local (PEN), se debe integrar pasarelas adquirentes peruanas y garantizar que los fondos de los jugadores radiquen en cuentas bancarias intangibles y separadas del capital de trabajo del operador, según exige la normativa para asegurar el pago de premios.

---

### Conclusión

TITANBET presenta una **base arquitectónica financiera de grado bancario**. Sus esquemas de concurrencia robusta (Double-Entry, Select-for-Update) y registro inmutable (Hash Chaining) previenen fraudes internos y vulnerabilidades críticas comunes en desarrollos tempranos. Sin embargo, para transicionar de un proyecto académico a un operador legal bajo la Ley N° 31557, el roadmap a futuro requiere enfocar los esfuerzos en la integración con el Estado Peruano, la homologación del laboratorio certificador y el despliegue de validación de identidad avanzada.
