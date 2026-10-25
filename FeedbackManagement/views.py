"""
Feedback APIs — system feedback and improvements.
Any authenticated user can submit feedback with up to 3 images and a
description, and can comment on public feedback.
"""
from django.db import transaction
from django.db.models import Count
from PIL import Image, UnidentifiedImageError
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Feedback, FeedbackImage, FeedbackComment

MAX_IMAGES = 3
DESCRIPTION_MAX_LENGTH = 2000
COMMENT_MAX_LENGTH = 1500
COMMENTS_PER_PAGE = 20


def request_page(request):
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        raise ValidationError({"page": "Page must be a positive number."})
    if page < 1:
        raise ValidationError({"page": "Page must be a positive number."})
    return page


def validate_image(image, field_name):
    if not (image.content_type or '').startswith('image/'):
        raise ValidationError({field_name: f"'{image.name}' is not an image file."})
    if image.size > 5 * 1024 * 1024:
        raise ValidationError({field_name: f"'{image.name}' exceeds 5 MB."})
    try:
        Image.open(image).verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError({field_name: f"'{image.name}' is not a valid image."})
    finally:
        image.seek(0)


def request_image_url(image, request=None):
    """Return absolute image URL."""
    try:
        url = image.image.url if hasattr(image, 'image') else image.url
        if request and not url.startswith(('http://', 'https://')):
            return request.build_absolute_uri(url)
        return url
    except Exception:
        return None


def user_photo_url(user, request=None):
    if not user.photo:
        return None
    try:
        url = user.photo.url
        if request and not url.startswith(('http://', 'https://')):
            return request.build_absolute_uri(url)
        return url
    except Exception:
        return None


def comment_json(comment, request=None):
    img_url = None
    if comment.image:
        img_url = request_image_url(comment.image, request)
    return {
        "id": comment.id,
        "comment": comment.comment,
        "image_url": img_url,
        "author_name": comment.user.full_name or "Member",
        "author_photo_url": user_photo_url(comment.user, request),
        "is_author": (request.user.id == comment.user_id) if request and request.user.is_authenticated else False,
        "created_at": comment.created_at.isoformat(),
    }


def feedback_json(feedback, request=None):
    comments_count = feedback.comments_count_value if hasattr(feedback, 'comments_count_value') else feedback.comments.count()
    return {
        "id": feedback.id,
        "description": feedback.description,
        "is_public": feedback.is_public,
        "images": [
            url for url in (request_image_url(img, request) for img in feedback.images.all())
            if url is not None
        ],
        "author_name": feedback.user.full_name or "Member",
        "author_photo_url": user_photo_url(feedback.user, request),
        "is_author": (request.user.id == feedback.user_id) if request and request.user.is_authenticated else False,
        "created_at": feedback.created_at.isoformat(),
        "comments_count": comments_count,
        "comments": [],
    }


# ---------------------------------------------------------------------------
# User endpoints  (/api/v1/user/feedbacks)
# ---------------------------------------------------------------------------

class FeedbackListView(APIView):
    """
    GET  /api/v1/user/feedbacks          — list all system feedbacks
    POST /api/v1/user/feedbacks          — submit a new system feedback (multipart)
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        page = request_page(request)
        per_page = 20

        feedbacks = Feedback.objects.filter(is_public=True).annotate(
            comments_count_value=Count('comments')
        ).select_related('user').prefetch_related('images').order_by('-created_at', '-id')

        total = feedbacks.count()
        start = (page - 1) * per_page
        end = start + per_page
        items = feedbacks[start:end]

        return Response({
            "data": [feedback_json(fb, request) for fb in items],
            "next_page": page + 1 if end < total else None,
        })

    def post(self, request):
        description = (request.data.get('description') or '').strip()
        if not description:
            raise ValidationError({"description": "Description is required."})
        if len(description) > DESCRIPTION_MAX_LENGTH:
            raise ValidationError({"description": f"Description can't be longer than {DESCRIPTION_MAX_LENGTH} characters."})

        images = request.FILES.getlist('images')
        if len(images) > MAX_IMAGES:
            raise ValidationError({"images": f"You can upload at most {MAX_IMAGES} images."})

        for img in images:
            validate_image(img, 'images')

        with transaction.atomic():
            feedback = Feedback.objects.create(
                user=request.user,
                description=description,
            )
            for img in images:
                FeedbackImage.objects.create(feedback=feedback, image=img)

        feedback.refresh_from_db()
        return Response(feedback_json(feedback, request), status=status.HTTP_201_CREATED)


class FeedbackCommentListView(APIView):
    """
    GET  /api/v1/user/feedbacks/<feedback_id>/comments   — list comments
    POST /api/v1/user/feedbacks/<feedback_id>/comments  — add a comment (with optional image)
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, feedback_id):
        feedback = Feedback.objects.filter(pk=feedback_id, is_public=True).first()
        if not feedback:
            raise NotFound("Feedback not found.")
        page = request_page(request)
        comments = feedback.comments.select_related('user').all()
        total = comments.count()
        start = (page - 1) * COMMENTS_PER_PAGE
        end = start + COMMENTS_PER_PAGE
        items = comments[start:end]
        return Response({
            "data": [comment_json(c, request) for c in items],
            "comments_count": total,
            "next_page": page + 1 if end < total else None,
        })

    def post(self, request, feedback_id):
        feedback = Feedback.objects.filter(pk=feedback_id, is_public=True).first()
        if not feedback:
            raise NotFound("Feedback not found.")

        comment_text = (request.data.get('comment') or '').strip()
        image = request.FILES.get('image')

        if not comment_text and not image:
            raise ValidationError({"comment": "Please enter a comment or attach an image."})
        if comment_text and len(comment_text) > COMMENT_MAX_LENGTH:
            raise ValidationError({"comment": f"Comment can't be longer than {COMMENT_MAX_LENGTH} characters."})

        if image:
            validate_image(image, 'image')

        comment = FeedbackComment.objects.create(
            feedback=feedback,
            user=request.user,
            comment=comment_text,
            image=image,
        )
        return Response(comment_json(comment, request), status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Admin endpoints  (/api/v1/admin/feedbacks)
# ---------------------------------------------------------------------------

class AdminFeedbackListView(APIView):
    """
    GET    /api/v1/admin/feedbacks       — list all system feedbacks (staff)
    DELETE /api/v1/admin/feedbacks/<id>   — delete a feedback
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        page = request_page(request)
        per_page = 20
        feedbacks = Feedback.objects.all().annotate(comments_count_value=Count('comments')).select_related('user').prefetch_related('images').order_by('-created_at', '-id')
        total = feedbacks.count()
        start = (page - 1) * per_page
        end = start + per_page
        items = feedbacks[start:end]

        return Response({
            "data": [feedback_json(fb, request) for fb in items],
            "next_page": page + 1 if end < total else None,
        })


class AdminFeedbackDeleteView(APIView):
    """DELETE /api/v1/admin/feedbacks/<id>"""
    permission_classes = [permissions.IsAdminUser]

    def delete(self, request, pk):
        feedback = Feedback.objects.filter(pk=pk).first()
        if not feedback:
            raise NotFound("Feedback not found.")
        feedback.delete()
        return Response({"message": "Feedback deleted."})
