import traceback

from django.http import JsonResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .serializers import (
    MessCreationSerializer,
    MessMemberShipSerializer,
    MessSeasonSerializer,
    MessSerializer,
)


def MessManagementTest(request):
    return JsonResponse({"message": "Mess Management API is working!"})


class MessCreationView(generics.CreateAPIView):
    """
    POST /api/v1/mess/create/

    Atomically creates a Mess, its first Season, and the creator's
    Membership.  The authenticated user automatically becomes the
    manager and acting-manager of the new mess.
    """
    serializer_class = MessCreationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = serializer.save()

            return Response(
                {
                    "message": "Mess created successfully.",
                    "mess": MessSerializer(result['mess']).data,
                    "season": MessSeasonSerializer(result['season']).data,
                    "membership": MessMemberShipSerializer(result['membership']).data,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {
                    "error": str(e),
                    "detail": traceback.format_exc(),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )