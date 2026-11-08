from django.core.management.base import BaseCommand
from apps.identity.infrastructure.services.administrativePanel import prepareSetup

class Command(BaseCommand):
    help = 'Prepare only the explicitly selected existing owner; no passwords or roles are changed.'
    def add_arguments(self, parser):
        parser.add_argument('--owner', required=True)
    def handle(self, *args, **options):
        result = prepareSetup(options['owner'])
        self.stdout.write('ADMINISTRATIVE_SETUP_PREPARED')
