import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Check the configured Places search key without printing the key.'

    def handle(self, *args, **options):
        key = settings.GOOGLE_MAPS_API_KEY.strip()
        if not key:
            raise CommandError('GOOGLE_MAPS_API_KEY is missing from the backend environment.')
        request = Request(
            'https://places.googleapis.com/v1/places:searchText',
            data=json.dumps({'textQuery': 'Dhaka', 'maxResultCount': 1}).encode(),
            headers={
                'Content-Type': 'application/json',
                'X-Goog-Api-Key': key,
                'X-Goog-FieldMask': 'places.displayName,places.formattedAddress,places.location',
            },
            method='POST',
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
        except HTTPError as error:
            try:
                details = json.loads(error.read().decode()).get('error', {})
            except (ValueError, UnicodeDecodeError):
                raise CommandError(f'Google returned HTTP {error.code}, without a readable error.') from None
            reasons = [item.get('reason', '') for item in details.get('details', []) if item.get('reason')]
            message = str(details.get('message', 'Request rejected.')).replace(key, '[REDACTED]')
            raise CommandError(f'Google HTTP {error.code}: {details.get("status", "UNKNOWN")}\nReasons: {", ".join(reasons) or "not provided"}\n{message}') from None
        except (URLError, TimeoutError):
            raise CommandError('Cannot reach Google Places: check network, DNS, proxy, or firewall.') from None
        except (ValueError, UnicodeDecodeError):
            raise CommandError('Google returned an unreadable response.') from None
        self.stdout.write(self.style.SUCCESS(f'Places search works. Returned {len(data.get("places", []))} result(s).'))
