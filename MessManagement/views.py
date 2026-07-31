import traceback

from django.http import JsonResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Mess
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