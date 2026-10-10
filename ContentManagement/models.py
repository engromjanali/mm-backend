from django.core.cache import cache
import re
from urllib.parse import quote, urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator, URLValidator, validate_email
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

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


def validate_support_logo(value):
    if value.size > 2 * 1024 * 1024:
        raise ValidationError('Use a logo smaller than 2 MB.')


class SupportChannel(models.Model):
    KINDS = [('email', 'Email'), ('telegram', 'Telegram'), ('whatsapp', 'WhatsApp'), ('phone', 'Phone'), ('website', 'Website'), ('other', 'Other')]

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=KINDS)
    destination = models.CharField(max_length=500, help_text='Email address, Telegram username or https://t.me link, phone number (WhatsApp needs country code), or an HTTP/HTTPS link.')
    logo = models.ImageField(upload_to='support_logos/', blank=True, validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp']), validate_support_logo], help_text='Optional PNG, JPEG or WebP, up to 2 MB.')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'support_channels'
        ordering = ['order', 'id']

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        self.destination = self.destination.strip()
        try:
            if self.kind == 'email':
                validate_email(self.destination)
            elif self.kind in {'phone', 'whatsapp'}:
                self.destination = re.sub(r'[\s()-]', '', self.destination)
                pattern = r'\+?[1-9]\d{6,14}' if self.kind == 'whatsapp' else r'\+?\d{6,15}'
                if not re.fullmatch(pattern, self.destination):
                    raise ValidationError('Enter a valid phone number. WhatsApp numbers must include the country code, without a leading zero.')
            elif self.kind == 'telegram' and not self.destination.startswith('https://'):
                self.destination = self.destination.lstrip('@')
                if not re.fullmatch(r'[A-Za-z0-9_]{5,32}', self.destination):
                    raise ValidationError('Enter a Telegram username or an https://t.me link.')
            else:
                URLValidator(schemes=['http', 'https'])(self.destination)
                parsed = urlsplit(self.destination)
                if parsed.username or parsed.password:
                    raise ValidationError('Links must not contain login credentials.')
                if self.kind == 'telegram' and (parsed.scheme != 'https' or parsed.hostname != 't.me' or not parsed.path.strip('/')):
                    raise ValidationError('Use an https://t.me link.')
        except ValidationError as error:
            raise ValidationError({'destination': error.messages}) from error

    @property
    def contact_url(self):
        if self.kind == 'email':
            return f'mailto:{quote(self.destination, safe="@.+")}'
        if self.kind == 'phone':
            return f'tel:{self.destination}'
        if self.kind == 'whatsapp':
            return f'https://wa.me/{self.destination.lstrip("+")}'
        if self.kind == 'telegram' and not self.destination.startswith('https://'):
            return f'https://t.me/{self.destination}'
        return self.destination

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        old_logo = SupportChannel.objects.filter(pk=self.pk).values_list('logo', flat=True).first() if self.pk and (update_fields is None or 'logo' in update_fields) else None
        super().save(*args, **kwargs)
        if old_logo and old_logo != self.logo.name:
            storage = self.logo.storage
            transaction.on_commit(lambda: storage.delete(old_logo))


@receiver(post_delete, sender=SupportChannel)
def delete_support_logo(sender, instance, **kwargs):
    if instance.logo:
        storage, name = instance.logo.storage, instance.logo.name
        transaction.on_commit(lambda: storage.delete(name))
