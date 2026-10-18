# ADR-003: Versión global y borrado lógico

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

El Edge pide cambios con `since_version`. Un `version = 1` por fila, como proponía la especificación, no permite ordenar cambios de empleados, credenciales, puertas y perfiles en una sola secuencia. Un `DELETE` físico tampoco viajaría en el delta: la credencial seguiría abriendo puertas en el nodo.

La secuencia tiene que ser global, no por organización, porque un nodo solo recibe las filas de su organización aunque los números se intercalen con los de otras.

## Decisión

PostgreSQL mantiene la secuencia `sync_version_seq`. El trigger `assign_sync_version` asigna `nextval` en cada `INSERT` o `UPDATE` de las tablas sincronizables: departamento, empleado, credencial, zona, perfil de lector, puerta y lector. Cubre `save()`, `bulk_update` y `QuerySet.update`.

`SyncableModel.save()` relee `version` después de escribir. Los huecos de la secuencia son aceptables: `nextval` no se revierte con la transacción.

Las filas sincronizables no se borran. `DELETE` de la API marca `is_active = false` y `deleted_at`. La versión nueva propaga la baja. La credencial activa es única por `(organization, type, payload)`; al desactivarla el valor puede reutilizarse. El documento del empleado sigue siendo único dentro de la organización aunque el empleado esté inactivo.

`Employee.is_inside` también consume versión cuando cambia. El delta de la Fase 2 puede volver ruidoso si cada marcación reescribe al empleado. Si eso estorba, un cambio posterior puede excluir esa columna del trigger sin abandonar la secuencia global.

## Consecuencias

- Cualquier mutación de empleado, credencial, puerta o perfil aumenta la versión de forma monótona en toda la instalación.
- Las pruebas de esta fase exigen PostgreSQL: la secuencia y el índice único parcial no tienen el mismo comportamiento en SQLite.
- La Fase 2 filtra el delta por la organización del nodo y debe incluir filas inactivas.
