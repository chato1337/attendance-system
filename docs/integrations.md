# Integraciones: webhooks y API de ERP

Contrato de la Fase 8. Cada suscripción y cada token pertenecen a una
organización; el payload siempre incluye `organization_id`.

## Webhooks

### Suscripción

```http
POST /api/v1/webhooks/
Authorization: Bearer <jwt>
```

```json
{
  "name": "Nómina",
  "url": "https://erp.example.com/hooks/attendance",
  "events": ["access.granted", "access.denied", "device.status_changed"],
  "is_active": true
}
```

La respuesta incluye `secret_value` **una sola vez**. Guárdelo: se usa para
verificar la firma. Puede rotarlo con `POST /api/v1/webhooks/{id}/regenerate-secret/`.

Eventos iniciales:

| Evento | Cuándo |
| --- | --- |
| `access.granted` / `access.denied` | Al persistir un `AccessLog` |
| `device.status_changed` | Cuando un nodo pasa a online/offline |

El catálogo admite sin código adicional: `employee.updated`, `occupancy.threshold`,
`face.enrolled` (aún no se emiten).

### Cabeceras de entrega

| Cabecera | Valor |
| --- | --- |
| `Content-Type` | `application/json` |
| `X-Event` | Nombre del evento |
| `X-Delivery-Id` | UUID de la entrega |
| `X-Organization-Id` | UUID de la organización |
| `X-Signature` | `sha256=<HMAC-SHA256(secret, body)>` |

Timeout: 10 s. Reintentos: hasta 8, con esperas 1 min → 24 h. Códigos HTTP 2xx
marcan la entrega como `SUCCESS`; el resto reintenta hasta `EXHAUSTED`.

### Verificar la firma (Python)

```python
import hashlib, hmac

def verify(secret: str, body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")
```

### Verificar la firma (Node.js)

```js
const crypto = require("crypto");

function verify(secret, body, header) {
  const expected =
    "sha256=" + crypto.createHmac("sha256", secret).update(body).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(header || ""));
}
```

### Panel

- CRUD de suscripciones, log de entregas, «enviar evento de prueba» y «reenviar».
- `GET /api/v1/webhooks/{id}/deliveries/`
- `POST /api/v1/webhook-deliveries/{id}/resend/`

## Tokens de API

```http
POST /api/v1/api-tokens/
Authorization: Bearer <jwt admin>
```

```json
{
  "name": "Conector Siigo",
  "scopes": ["employees:read", "employees:write"]
}
```

El token (`atk_…`) se muestra una sola vez. Úselo como:

```http
Authorization: Bearer atk_…
```

Alcances:

| Alcance | Permite |
| --- | --- |
| `employees:read` | Listar/consultar empleados |
| `employees:write` | Crear, editar e importar empleados |
| `webhooks:manage` | Administrar suscripciones y reenvíos |

## Importación masiva de empleados

```http
POST /api/v1/employees/bulk/
Authorization: Bearer <jwt|atk_… con employees:write>
Content-Type: application/json
```

```json
{
  "employees": [
    {
      "document_id": "123",
      "first_name": "Ana",
      "last_name": "Ruiz",
      "email": "ana@acme.test",
      "department": "Operaciones",
      "is_active": true
    }
  ]
}
```

También acepta CSV (`Content-Type: text/csv` o multipart `file`) con las mismas
columnas. Máximo 2000 filas. El departamento se crea si no existe (por nombre).
La respuesta indica `created`, `updated` y `errors` por índice.

## Conector de ejemplo

Un ERP genérico (Odoo/Siigo u otro) puede:

1. Crear un token con `employees:write` e importar el maestro de personal por lotes.
2. Suscribirse a `access.granted` / `access.denied` para reflejar marcaciones en nómina.
3. Verificar `X-Signature` antes de procesar el cuerpo.

La elección del ERP concreto queda abierta (P7); este contrato no cambia.
