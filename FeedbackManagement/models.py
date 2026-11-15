from django.conf import settings
from django.db import models


class Feedback(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feedbacks')
    description = models.TextField(max_length=2000)
    is_public = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"Feedback #{self.id} by {self.user}"


class FeedbackImage(models.Model):
    feedback = models.ForeignKey(Feedback, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='feedback/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image #{self.id} for Feedback #{self.feedback_id}"


class FeedbackComment(models.Model):
    feedback = models.ForeignKey(Feedback, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feedback_comments')
    comment = models.TextField(max_length=1500)
    image = models.ImageField(upload_to='feedback_comments/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment #{self.id} on Feedback #{self.feedback_id} by {self.user}"
