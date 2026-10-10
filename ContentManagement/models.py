from django.core.cache import cache
from django.core.validators import RegexValidator
from django.db import models

LANGUAGES = [('en', 'English'), ('bn', 'Bengali'), ('ar', 'Arabic')]
DEFAULT_LANGUAGE = 'en'

version_validator = RegexValidator(r'^\d+(\.\d+){0,2}$', 'Use a version like 1.4.2.')


class AppSetting(models.Model):
    """
    App-wide settings the admin changes in Django admin, served to the app by
    ``/api/v1/app/config``. A single row (pk 1); use ``AppSetting.current()``.
    """
    CACHE_KEY = 'app_setting'
    CACHE_SECONDS = 30

    latest_version = models.CharField(max_length=20, default='1.0.0', validators=[version_validator], help_text="Newest app version. Older apps are offered an optional update.")
    minimum_version = models.CharField(max_length=20, default='1.0.0', validators=[version_validator], help_text="Apps older than this must update before they can be used.")
    update_message = models.TextField(blank=True, help_text="Shown with the update prompt. Leave empty for the app's default text.")
    android_store_url = models.URLField(blank=True)
    ios_store_url = models.URLField(blank=True)

    maintenance_mode = models.BooleanField(default=False, help_text="While on, the app shows the maintenance screen and the API answers 503.")
    maintenance_message = models.TextField(blank=True, default="We're improving the app. Please check back soon.")
    maintenance_until = models.DateTimeField(null=True, blank=True, help_text="Expected end, shown to users. Optional.")

    support_email = models.EmailField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'app_settings'
        verbose_name = 'App setting'
        verbose_name_plural = 'App settings'

    def __str__(self):
        return 'App settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    @classmethod
    def current(cls):
        """The settings row (created with defaults on first use), cached briefly since every API call reads it."""
        setting = cache.get(cls.CACHE_KEY)
        if setting is None:
            setting, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls.CACHE_KEY, setting, cls.CACHE_SECONDS)
        return setting


class ContentPage(models.Model):
    """Privacy policy / terms and conditions text, one per language."""
    PRIVACY_POLICY = 'privacy-policy'
    TERMS = 'terms-and-conditions'
    KINDS = [(PRIVACY_POLICY, 'Privacy policy'), (TERMS, 'Terms and conditions')]

    kind = models.CharField(max_length=40, choices=KINDS)
    language = models.CharField(max_length=5, choices=LANGUAGES, default=DEFAULT_LANGUAGE)
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Plain text. Separate paragraphs with a blank line; a line starting with '# ' is a heading and '- ' a bullet.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'content_pages'
        constraints = [models.UniqueConstraint(fields=['kind', 'language'], name='one_page_per_kind_and_language')]
        ordering = ['kind', 'language']

    def __str__(self):
        return f'{self.get_kind_display()} ({self.language})'


class Faq(models.Model):
    """A frequently asked question; shown in ``order``, per language."""
    language = models.CharField(max_length=5, choices=LANGUAGES, default=DEFAULT_LANGUAGE)
    question = models.CharField(max_length=300)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0, help_text="Lower comes first.")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'faqs'
        ordering = ['order', 'id']
        verbose_name = 'FAQ'
        verbose_name_plural = 'FAQs'

    def __str__(self):
        return self.question
