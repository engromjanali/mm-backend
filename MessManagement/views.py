import traceback

from django.http import JsonResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Mess, MessMemberShipRequest, Notices
from .serializers import (
    MessCreationSerializer,
    MessMemberShipSerializer,
    MessMemberShipRequestSerializer,
    MessSeasonSerializer,
    MessSerializer,
    NoticesSerializer,
)
from .utils import get_verified_membership_and_season


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


class MessListView(generics.ListAPIView):
    """
    GET /api/v1/mess/list

    Retrieves a list of messes:
    - If `search` query parameter is missing: returns all messes.
    - If `search` exists and has non-empty keyword: returns matched messes.
    - If `search` exists but is empty/whitespace: returns no results.

    Slices results based on offset (page) and limit parameters, returning formatted output:
    {
      "total_size": int,
      "data": []
    }
    """
    serializer_class = MessSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        queryset = Mess.objects.all().order_by('name')
        
        # 1. Handle Search Parameter Rules
        if 'search' in request.query_params:
            search_val = request.query_params.get('search', '')
            cleaned_val = search_val.strip()
            if not cleaned_val:
                return Response({
                    "total_size": 0,
                    "data": []
                })
            queryset = queryset.filter(name__icontains=cleaned_val)
            
        # Get count of matching records before pagination slicing
        total_size = queryset.count()
        
        # 2. Handle Pagination Parameter Rules
        try:
            limit = int(request.query_params.get('limit', 20))
            if limit < 1:
                limit = 20
        except ValueError:
            limit = 20
            
        try:
            offset = int(request.query_params.get('offset', 1))
            if offset < 1:
                offset = 1
        except ValueError:
            offset = 1
            
        start = (offset - 1) * limit
        end = start + limit
        
        sliced_qs = queryset[start:end]
        serializer = self.get_serializer(sliced_qs, many=True)
        
        return Response({
            "total_size": total_size,
            "data": serializer.data
        })


class MessJoinRequestView(generics.CreateAPIView):
    """
    POST /api/v1/mess/join/

    Allows an authenticated user to submit a join request to a specific mess.
    Automatically status is 'pending' by default and user is the logged-in user.
    """
    serializer_class = MessMemberShipRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ---------------------------------------------------------------------------
# Notice APIs
# ---------------------------------------------------------------------------

class NoticeCreateView(APIView):
    """
    POST /api/v1/notice/create
    Creates a new notice for the mess associated with the user's active membership & session.
    Requires Manager or Acting Manager role.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=True)
        
        serializer = NoticesSerializer(data=request.data)
        if serializer.is_valid():
            is_pinned = serializer.validated_data.get('is_pinned', False)
            if is_pinned:
                Notices.objects.filter(mess=membership.mess, is_pinned=True).update(is_pinned=False)
            notice = serializer.save(mess=membership.mess)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NoticeUpdateView(APIView):
    """
    PUT/PATCH/POST /api/v1/notice/update or /api/v1/notice/update/<int:pk>/
    Updates an existing notice for the mess.
    Requires Manager or Acting Manager role.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _update_notice(self, request, pk=None, partial=False):
        membership, season = get_verified_membership_and_season(request, require_write=True)
        notice_id = pk or request.data.get('id') or request.data.get('notice_id')
        if not notice_id:
            return Response({"error": "Notice ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            notice = Notices.objects.get(id=notice_id, mess=membership.mess)
        except Notices.DoesNotExist:
            return Response({"error": "Notice not found in your mess."}, status=status.HTTP_404_NOT_FOUND)

        serializer = NoticesSerializer(notice, data=request.data, partial=partial)
        if serializer.is_valid():
            if serializer.validated_data.get('is_pinned', False):
                Notices.objects.filter(mess=membership.mess, is_pinned=True).exclude(id=notice.id).update(is_pinned=False)
            notice = serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk=None, *args, **kwargs):
        return self._update_notice(request, pk=pk, partial=False)

    def patch(self, request, pk=None, *args, **kwargs):
        return self._update_notice(request, pk=pk, partial=True)

    def post(self, request, pk=None, *args, **kwargs):
        return self._update_notice(request, pk=pk, partial=True)


class NoticeDeleteView(APIView):
    """
    DELETE/POST /api/v1/notice/delete or /api/v1/notice/delete/<int:pk>/
    Deletes a notice.
    Requires Manager or Acting Manager role.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _delete_notice(self, request, pk=None):
        membership, season = get_verified_membership_and_season(request, require_write=True)
        notice_id = pk or request.data.get('id') or request.data.get('notice_id')
        if not notice_id:
            return Response({"error": "Notice ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            notice = Notices.objects.get(id=notice_id, mess=membership.mess)
        except Notices.DoesNotExist:
            return Response({"error": "Notice not found in your mess."}, status=status.HTTP_404_NOT_FOUND)

        notice.delete()
        return Response({"message": "Notice deleted successfully."}, status=status.HTTP_200_OK)

    def delete(self, request, pk=None, *args, **kwargs):
        return self._delete_notice(request, pk=pk)

    def post(self, request, pk=None, *args, **kwargs):
        return self._delete_notice(request, pk=pk)


class NoticeListView(APIView):
    """
    GET /api/v1/notice/list
    Lists all notices for the authenticated user's mess with limit & offset pagination.
    Accessible to all active members of the mess.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=False)
        queryset = Notices.objects.filter(mess=membership.mess).order_by('-created_at')

        total_size = queryset.count()

        try:
            limit = int(request.query_params.get('limit', 20))
            if limit < 1:
                limit = 20
        except ValueError:
            limit = 20

        try:
            offset = int(request.query_params.get('offset', 1))
            if offset < 1:
                offset = 1
        except ValueError:
            offset = 1

        start = (offset - 1) * limit
        end = start + limit

        sliced_qs = queryset[start:end]
        serializer = NoticesSerializer(sliced_qs, many=True)

        return Response({
            "total_size": total_size,
            "data": serializer.data
        })


class NoticeDetailView(APIView):
    """
    GET /api/v1/notice/{id}
    Retrieves a single notice by ID.
    Accessible to all active members of the mess.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=False)
        try:
            notice = Notices.objects.get(id=pk, mess=membership.mess)
        except Notices.DoesNotExist:
            return Response({"error": "Notice not found in your mess."}, status=status.HTTP_404_NOT_FOUND)

        serializer = NoticesSerializer(notice)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NoticePinnedView(APIView):
    """
    GET /api/v1/notice/pin
    Retrieves the currently pinned notice for the mess.
    Accessible to all active members of the mess.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=False)
        pinned_notice = Notices.objects.filter(mess=membership.mess, is_pinned=True).first()

        if not pinned_notice:
            return Response({"message": "No pinned notice found", "data": None}, status=status.HTTP_200_OK)

        serializer = NoticesSerializer(pinned_notice)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NoticeSetPinnedView(APIView):
    """
    POST /api/v1/notice/set-pined-notice
    Pins a specific notice and unpins any previously pinned notice in the mess.
    Requires Manager or Acting Manager role.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        membership, season = get_verified_membership_and_season(request, require_write=True)
        notice_id = request.data.get('notice_id') or request.data.get('id')

        if not notice_id:
            return Response({"error": "notice_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            notice = Notices.objects.get(id=notice_id, mess=membership.mess)
        except Notices.DoesNotExist:
            return Response({"error": "Notice not found in your mess."}, status=status.HTTP_404_NOT_FOUND)

        # Unpin any currently pinned notice in this mess
        Notices.objects.filter(mess=membership.mess, is_pinned=True).update(is_pinned=False)

        notice.is_pinned = True
        notice.save()

        serializer = NoticesSerializer(notice)
        return Response({
            "message": "Notice pinned successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)