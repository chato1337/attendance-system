from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "El registro viola una restricción de unicidad."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, DjangoValidationError):
        messages = exc.messages if hasattr(exc, "messages") else [str(exc)]
        return Response({"detail": messages}, status=status.HTTP_400_BAD_REQUEST)
    response = exception_handler(exc, context)
    if response is None or not isinstance(response.data, dict):
        return response
    if response.status_code == 404:
        response.data["detail"] = "No encontrado."
    return response
