# Panel web

Operación del dominio desde el navegador: sesión JWT, selector de organización, tablero en vivo, empleados y credenciales, nodos, puertas, perfiles de lector, marcaciones, anomalías, enrolamiento asistido, kioscos y membresías.

## Arranque

```bash
cd frontend
npm ci
npm test
npm run dev
```

La aplicación queda en http://localhost:5173. La API se toma de `VITE_API_URL` (por defecto `http://localhost:8000/api/v1`; ver `.env.example`). El tablero abre `VITE_WS_URL` (por defecto `ws://localhost:8001`) en `/ws/dashboard/`.

Con los datos de `seed_demo`, entre como `acme.operator` / `Nube-Segura-2026!`. `multi.admin` elige organización al entrar. `superadmin` administra las organizaciones.

## Estructura

- `src/api`: cliente Axios (refresh automático) y tipos alineados con los serializers.
- `src/auth`: sesión y preferencias en Zustand, persistidas en el navegador.
- `src/pages`: pantallas. La organización activa forma parte de la clave de TanStack Query; al cambiarla se vacía la caché.
- `src/components`: layout, formularios y piezas de interfaz.

Los formularios usan `react-hook-form` y `zod`. Un perfil de consulta ve los datos y no ve las acciones de escritura. El operador da de alta empleados, credenciales, puertas y perfiles, abre puertas y enrola. El administrador, además, gestiona nodos, kioscos y membresías.

La llave de un nodo y el token de un kiosco se muestran una sola vez, al crearlos o regenerarlos. Las lecturas del enrolamiento asistido llegan por `GET /api/v1/enrollment-reads/`.

## Tipos desde OpenAPI

```bash
npm run generate:api
```

Lee `http://localhost:8000/api/schema/?format=json` (o `API_SCHEMA_URL`) y escribe `src/api/schema.d.ts` como referencia. El cliente que usa el panel es `src/api/types.ts` junto con `src/api/client.ts`; hay que mantenerlos al día cuando cambie el contrato.

## Pruebas

```bash
npm test
npm run test:e2e
```

Vitest cubre el ingreso, el bloqueo por rol y el alta de empleado con credencial. Playwright recorre ese mismo flujo contra el servidor de desarrollo, con la API simulada en el navegador.
