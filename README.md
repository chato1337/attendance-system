# Sistema de Control y Registro de Acceso

Sistema multi-tenant para registrar y controlar el acceso físico de los colaboradores de varias organizaciones. La nube es la fuente de verdad. Cada sede tendrá un agente que valida credenciales locales sin Internet. El reconocimiento facial, cuando se habilite, usa el servicio externo Face-Auth.

El plan vivo está en [`docs/development-plan.md`](docs/development-plan.md). Las decisiones cerradas están en [`docs/adr`](docs/adr).

## Qué hay en esta versión

- **API** (Django REST Framework) con organizaciones, usuarios, empleados, credenciales, nodos, puertas, lectores, perfiles de lector, zonas, kioscos y la configuración de Face-Auth.
- **Panel** con la pantalla inicial. El CRUD visual llega en una fase posterior; mientras tanto la API se prueba en Swagger.
- **Agente Edge** con el módulo Go compilando. La validación offline llega con el agente.

## Requisitos

- Docker y Docker Compose
- Para trabajar sin los contenedores de la app: Python 3.12+, Node.js 22 y Go 1.23+

## Levantar todo

```bash
docker compose -f infra/docker-compose.yml up --build
```

En otra terminal, cargue los datos de demostración:

```bash
docker compose -f infra/docker-compose.yml exec api python manage.py seed_demo
```

| Servicio | Dirección |
| --- | --- |
| Swagger | http://localhost:8000/api/schema/swagger-ui/ |
| Salud de la API | http://localhost:8000/api/v1/health/ |
| Panel | http://localhost:5173 |
| Nginx (API y panel) | http://localhost:8080 |
| Admin de Django | http://localhost:8000/admin/ |

La contraseña de todos los usuarios demo es `Nube-Segura-2026!`.

| Usuario | Alcance |
| --- | --- |
| `superadmin` | Plataforma. Crea organizaciones. |
| `acme.admin` | Administrador de Acme |
| `acme.operator` | Operador de Acme |
| `acme.viewer` | Solo consulta en Acme |
| `globex.admin` | Administrador de Globex |
| `multi.admin` | Administrador de Acme y de Globex. Tras entrar debe elegir organización. |

Un usuario con una sola organización recibe el `org_id` en el token. Con varias, `POST /api/v1/auth/switch-organization/` emite un token nuevo. A partir de ahí el claim `org_id` define qué datos puede ver.

## Roles

| Acción | Consulta | Operador | Administrador | Superadmin |
| --- | --- | --- | --- | --- |
| Leer el dominio de su organización | sí | sí | sí | sí, dentro de la organización elegida |
| Empleados, credenciales, puertas, perfiles y zonas | no | sí | sí | sí |
| Nodos, kioscos, membresías y Face-Auth | no | no | sí | sí |
| Organizaciones | no | no | no | sí |

La llave de un nodo y el token de un kiosco se muestran solo al crearlos o regenerarlos. La `api_key` de Face-Auth se escribe y no se vuelve a leer.

## Pruebas

```bash
docker compose -f infra/docker-compose.yml up -d db
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
POSTGRES_PORT=5433 .venv/bin/pytest
cd ../frontend && npm ci && npm test
cd ../edge && go test ./...
```

PostgreSQL del Compose se publica en el puerto **5433** para no ocupar el 5432 del sistema. Dentro de la red de Compose la API sigue usando el puerto 5432 del servicio `db`. Solo el contenedor `api` aplica migraciones; el worker y Channels esperan a que esa API esté sana.

## Estructura

```text
backend/     API, modelos y pruebas
frontend/    Panel React
edge/        Agente Go
infra/       Docker Compose y Nginx
docs/        Especificación, plan y ADRs
```

Las variables de entorno están documentadas en [`.env.example`](.env.example). `FACEAUTH_WEB_URL` y `FACEAUTH_API_URL` son los valores por defecto de la plataforma. El `app_id` y la `api_key` de cada organización se guardan en la base, no en el entorno.
