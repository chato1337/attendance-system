from drf_spectacular.utils import extend_schema
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.integrations.faceauth.enrollment import (
    authorize_session,
    begin_enrollment,
    complete_enrollment,
    enrollment_payload,
    fail_enrollment,
    load_session,
)
from apps.integrations.faceauth.flow import (
    FaceFlowError,
    hosted_url,
    integration_ready,
    load_integration,
)
from apps.integrations.faceauth.identify import identification_body, identify_face
from apps.kiosk.authentication import (
    KioskTokenAuthentication,
    PanelOrKioskAuthentication,
    touch_kiosk,
)
from apps.kiosk.models import FaceEnrollmentSession
from apps.kiosk.serializers import (
    EnrollmentFailSerializer,
    FaceIdentifyResponseSerializer,
    KioskHeartbeatSerializer,
    KioskLookupSerializer,
    KioskMeSerializer,
    RedirectTokenSerializer,
)
from apps.people.models import Employee


class KioskRateThrottle(SimpleRateThrottle):
    scope = "kiosk"

    def get_cache_key(self, request, view):
        kiosk = getattr(getattr(request, "user", None), "kiosk", None)
        if kiosk is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": kiosk.pk}


class KioskLookupThrottle(KioskRateThrottle):
    scope = "kiosk_lookup"


class KioskIdentifyThrottle(KioskRateThrottle):
    scope = "kiosk_identify"


def _face_error(exc: FaceFlowError) -> Response:
    body = {"code": exc.code, "detail": exc.detail}
    if exc.issues:
        body["issues"] = exc.issues
    return Response(body, status=exc.status)


class KioskMeView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [KioskRateThrottle]

    @extend_schema(tags=["Kiosco"], responses=KioskMeSerializer)
    def get(self, request):
        kiosk = request.user.kiosk
        touch_kiosk(kiosk)
        integration = load_integration(kiosk.organization_id)
        ready = integration_ready(integration)
        return Response(
            {
                "kiosk_id": kiosk.id,
                "name": kiosk.name,
                "door_id": kiosk.door_id,
                "door_name": kiosk.door.name,
                "direction": kiosk.door.direction,
                "organization_name": kiosk.organization.name,
                "organization_slug": kiosk.organization.slug,
                "face_enabled": bool(kiosk.door.face_enabled and ready),
                "faceauth_enabled": ready,
                "app_id": integration.app_id if ready else "",
                "api_url": integration.api_url if ready else "",
                "web_url": integration.web_url if integration else "",
                "allow_kiosk_self_enrollment": bool(
                    ready and integration.allow_kiosk_self_enrollment
                ),
                "camera_permission": kiosk.camera_permission,
            }
        )


class KioskHeartbeatView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [KioskRateThrottle]
    parser_classes = [JSONParser]

    @extend_schema(tags=["Kiosco"], request=KioskHeartbeatSerializer, responses=KioskMeSerializer)
    def post(self, request):
        serializer = KioskHeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kiosk = request.user.kiosk
        touch_kiosk(kiosk, serializer.validated_data["camera_permission"])
        return Response(
            {
                "camera_permission": kiosk.camera_permission,
                "last_seen_at": kiosk.last_seen_at,
            }
        )


class KioskFaceIdentifyView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [KioskIdentifyThrottle]
    parser_classes = [JSONParser]

    @extend_schema(
        tags=["Kiosco"],
        request=RedirectTokenSerializer,
        responses=FaceIdentifyResponseSerializer,
    )
    def post(self, request):
        serializer = RedirectTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            identified = identify_face(
                request.user.kiosk,
                serializer.validated_data["redirect_token"],
            )
        except FaceFlowError as exc:
            return _face_error(exc)
        return Response(identification_body(identified))


class KioskFaceIdentifyDetailView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [KioskRateThrottle]

    @extend_schema(tags=["Kiosco"], responses=FaceIdentifyResponseSerializer)
    def get(self, request, request_id):
        found = (
            request.user.kiosk.face_requests.filter(pk=request_id).first()
        )
        if found is None:
            return Response({"detail": "No encontrado."}, status=404)
        return Response(identification_body(found))


class KioskEmployeeLookupView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [KioskLookupThrottle]
    parser_classes = [JSONParser]

    @extend_schema(tags=["Kiosco"], request=KioskLookupSerializer)
    def post(self, request):
        serializer = KioskLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = Employee.objects.filter(
            document_id=serializer.validated_data["document_id"].strip(),
            is_active=True,
        ).first()
        if employee is None:
            return Response({"detail": "No encontrado."}, status=404)
        from apps.people.face import enrollment_blockers

        return Response(
            {
                "document_id": employee.document_id,
                "first_name": employee.first_name,
                "last_name": employee.last_name,
                "has_email": not enrollment_blockers(employee),
            }
        )


class KioskEnrollmentStartView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [KioskLookupThrottle]
    parser_classes = [JSONParser]

    @extend_schema(tags=["Kiosco"], request=KioskLookupSerializer)
    def post(self, request):
        kiosk = request.user.kiosk
        integration = load_integration(kiosk.organization_id)
        if not integration_ready(integration) or not integration.allow_kiosk_self_enrollment:
            return _face_error(
                FaceFlowError(
                    "self_enrollment_disabled",
                    "Este kiosco no permite registrar el rostro.",
                    403,
                )
            )
        serializer = KioskLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = Employee.objects.filter(
            document_id=serializer.validated_data["document_id"].strip(),
            is_active=True,
        ).first()
        if employee is None:
            return Response({"detail": "No encontrado."}, status=404)
        try:
            session = begin_enrollment(
                employee,
                started_by=FaceEnrollmentSession.StartedBy.KIOSK,
                kiosk=kiosk,
            )
        except FaceFlowError as exc:
            return _face_error(exc)
        return Response(enrollment_payload(session), status=201)


class KioskHostedStartView(APIView):
    authentication_classes = [KioskTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [KioskRateThrottle]

    @extend_schema(tags=["Kiosco"])
    def get(self, request):
        kiosk = request.user.kiosk
        try:
            integration = load_integration(kiosk.organization_id)
            if not integration_ready(integration):
                raise FaceFlowError(
                    "faceauth_disabled",
                    "El reconocimiento facial no está habilitado.",
                    409,
                )
            return Response({"url": hosted_url(integration, "kiosk")})
        except FaceFlowError as exc:
            return _face_error(exc)


class EnrollmentCompleteView(APIView):
    authentication_classes = [PanelOrKioskAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(tags=["Enrolamiento facial"], request=RedirectTokenSerializer)
    def post(self, request, session_id):
        return _session_action(request, session_id, complete=True)


class EnrollmentFailView(APIView):
    authentication_classes = [PanelOrKioskAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    @extend_schema(tags=["Enrolamiento facial"], request=EnrollmentFailSerializer)
    def post(self, request, session_id):
        return _session_action(request, session_id, complete=False)


class EnrollmentHostedStartView(APIView):
    authentication_classes = [PanelOrKioskAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Enrolamiento facial"])
    def get(self, request, session_id):
        try:
            session = load_session(session_id)
            authorize_session(request, session)
            integration = load_integration(session.organization_id)
            if not integration_ready(integration):
                raise FaceFlowError(
                    "faceauth_disabled",
                    "El reconocimiento facial no está habilitado.",
                    409,
                )
        except FaceFlowError as exc:
            return _face_error(exc)
        return Response({"url": hosted_url(integration, "enroll"), "session_id": str(session.id)})


def _session_action(request, session_id, *, complete: bool) -> Response:
    try:
        session = load_session(session_id)
        authorize_session(request, session)
        if complete:
            body = RedirectTokenSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            session = complete_enrollment(session, body.validated_data["redirect_token"])
        else:
            body = EnrollmentFailSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            session = fail_enrollment(
                session,
                body.validated_data["code"],
                body.validated_data.get("message", ""),
            )
    except FaceFlowError as exc:
        return _face_error(exc)
    return Response(enrollment_payload(session))
