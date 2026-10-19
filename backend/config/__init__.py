"""Proyecto Django del sistema de control de acceso."""

from config.celery import app as celery_app

__all__ = ("celery_app",)
