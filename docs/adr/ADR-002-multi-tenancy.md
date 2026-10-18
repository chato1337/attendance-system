# ADR-002: Multi-tenant con base de datos compartida

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

Una sola instalación debe alojar varias organizaciones. Un esquema PostgreSQL por cliente (`django-tenants`) complicaría la secuencia global de `version`, Celery y Channels. La especificación original no tenía dueño de los datos: `Employee.document_id` era único en toda la base y `AccessNode` no pertenecía a nadie.

## Decisión

Se usa una base compartida. Toda entidad de dominio lleva `organization_id`. Los únicos modelos globales son `Organization` y la cuenta de usuario. La relación entre ambos es `Membership(user, organization, role)` con roles `ADMIN`, `OPERATOR` y `VIEWER`.

El JWT del panel incluye `org_id`. La autenticación fija esa organización en el contexto de la petición. `TenantManager` filtra por ese contexto y, si no hay tenant, no devuelve filas. El acceso sin filtro existe solo como `Model.all_objects` para el admin operativo, las tareas y las pruebas. Las unicidades de documento y de credencial activa son por organización.

Un `SUPERADMIN` de plataforma administra organizaciones y puede entrar a una de ellas emitiendo un token con su `org_id`. No hay autorregistro. Un nodo pertenece a una sola organización.

## Consecuencias

- Una migración y un pool de conexiones para toda la instalación.
- El aislamiento es una regla de aplicación: cada consulta de dominio pasa por el manager y las pruebas cubren el cruce entre dos organizaciones.
- Los grupos de Channels y los webhooks, cuando existan, deben llevar el identificador de la organización.
- Los límites comerciales por plan quedan fuera de esta versión.
