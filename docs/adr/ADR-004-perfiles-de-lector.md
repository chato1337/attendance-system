# ADR-004: Perfiles de lector y payload normalizado

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

El agente no debe conocer marcas ni modelos. Cada lector entrega el identificador como texto (`hardware_read.data`) con un formato distinto: hexadecimal, decimal, ceros a la izquierda o un prefijo. La especificación asumía que el agente ya entendía el formato de cada credencial.

## Decisión

`ReaderProfile` define el tipo de credencial y una lista ordenada de pasos de normalización: `trim`, `upper`, `strip_leading_zeros`, `regex_extract`, `hex_to_dec`, `dec_to_hex` y `pad_left`, más una longitud mínima y máxima. `Reader` pertenece a una `Door` y apunta a un perfil. La credencial guarda el `payload` ya normalizado. La búsqueda local será por `(type, payload)`.

Cambiar de lector es cambiar configuración. El enrolamiento dirigido por comandos de un fabricante queda para la Fase 10. Hasta entonces, el enrolamiento asistido (Fase 3) muestra la lectura cruda y la normalizada para que un operador la asigne.

El backend expone `POST /api/v1/reader-profiles/{id}/preview`. Los casos compartidos viven en `docs/reader-profiles/normalization-cases.json` para que el intérprete Go de la Fase 3 use la misma semántica. Cada organización nueva recibe tres perfiles de ejemplo: RFID hexadecimal de 8 dígitos, RFID decimal de 10 dígitos e identificador numérico de lector de huella.

Para `FACIAL`, el payload no pasa por un perfil de lector: es el `user_id` UUID de Face-Auth (ADR-009).

## Consecuencias

- El agente permanece agnóstico del hardware.
- Un perfil mal escrito rechaza la lectura como mal formada en lugar de buscar una credencial arbitraria.
- La huella, cuando el lector entrega un template, se guarda como un valor no reversible declarado por el perfil; el matching 1:N ocurre en el lector.
