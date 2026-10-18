# Backend

API Django 5 y Django REST Framework. Desde la raíz del repositorio:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Las pruebas usan PostgreSQL 16. Con la base del compose en marcha:

```bash
docker compose -f ../infra/docker-compose.yml up -d db
pytest
ruff check .
ruff format --check .
```

`mypy` es opcional y no bloquea CI.

Datos de demostración, solo con `DEBUG=true`:

```bash
python manage.py seed_demo
```

La contraseña de los usuarios demo es `Nube-Segura-2026!`.
