from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from apps.betting.models import Sport, Event, Market, Selection, MarketType, EventStatus
from apps.users.models import User, AccountStatus, GamblingLimit, GamblingLimitType
from apps.wallet.models import WalletService


class Command(BaseCommand):
    help = 'Carga datos de prueba: eventos Mundial 2026, usuarios y fichas iniciales'

    def handle(self, *args, **options):
        self.stdout.write('Cargando datos de seed...')

        # Deporte
        football, _ = Sport.objects.get_or_create(
            slug='futbol', defaults={'name': 'Fútbol', 'icon': 'bi-trophy'}
        )

        # Eventos del Mundial 2026
        now = timezone.now()
        events_data = [
            ('Perú', 'Brasil', now + timedelta(hours=2), EventStatus.SCHEDULED,
             Decimal('3.80'), Decimal('3.40'), Decimal('2.00')),
            ('Argentina', 'Colombia', now + timedelta(hours=5), EventStatus.SCHEDULED,
             Decimal('1.75'), Decimal('3.60'), Decimal('4.50')),
            ('España', 'Francia', now - timedelta(minutes=30), EventStatus.LIVE,
             Decimal('2.30'), Decimal('3.20'), Decimal('3.10')),
            ('México', 'USA', now + timedelta(hours=24), EventStatus.SCHEDULED,
             Decimal('2.90'), Decimal('3.30'), Decimal('2.40')),
            ('Alemania', 'Italia', now + timedelta(hours=48), EventStatus.SCHEDULED,
             Decimal('2.10'), Decimal('3.40'), Decimal('3.50')),
            ('Japón', 'Corea del Sur', now + timedelta(hours=72), EventStatus.SCHEDULED,
             Decimal('2.50'), Decimal('3.20'), Decimal('2.80')),
        ]

        for home, away, when, status, odds_1, odds_x, odds_2 in events_data:
            event, created = Event.objects.get_or_create(
                home_team=home, away_team=away,
                defaults={
                    'sport': football, 'scheduled_at': when, 'status': status
                }
            )
            if created:
                # Mercado 1X2
                market = Market.objects.create(
                    event=event, market_type=MarketType.HOME_DRAW_AWAY
                )
                Selection.objects.create(market=market, name='1', odds=odds_1)
                Selection.objects.create(market=market, name='X', odds=odds_x)
                Selection.objects.create(market=market, name='2', odds=odds_2)

                # Mercado Over/Under 2.5
                ou_market = Market.objects.create(
                    event=event, market_type=MarketType.OVER_UNDER,
                    line=Decimal('2.5')
                )
                Selection.objects.create(
                    market=ou_market, name='Over 2.5', odds=Decimal('1.85')
                )
                Selection.objects.create(
                    market=ou_market, name='Under 2.5', odds=Decimal('2.00')
                )

                # Mercado BTTS
                btts_market = Market.objects.create(
                    event=event, market_type=MarketType.BTTS
                )
                Selection.objects.create(
                    market=btts_market, name='Sí', odds=Decimal('1.90')
                )
                Selection.objects.create(
                    market=btts_market, name='No', odds=Decimal('1.95')
                )

                self.stdout.write(f'  Evento creado: {event}')

        # Usuarios de prueba
        test_users = [
            ('jugador1', 'Test1234!', 'jugador1@test.com', '72345678', '1995-01-15'),
            ('jugador2', 'Test1234!', 'jugador2@test.com', '72345679', '1998-06-20'),
            ('jugador3', 'Test1234!', 'jugador3@test.com', '72345670', '2000-03-10'),
        ]

        for username, pwd, email, dni, birth in test_users:
            if not User.objects.filter(username=username).exists():
                user = User.objects.create_user(
                    username=username,
                    password=pwd,
                    email=email,
                    dni=dni,
                    birth_date=birth,
                    account_status=AccountStatus.VERIFIED,
                )
                # Límites por defecto
                GamblingLimit.objects.create(
                    user=user, limit_type=GamblingLimitType.DAILY,
                    amount=Decimal('500.0000'),
                )
                GamblingLimit.objects.create(
                    user=user, limit_type=GamblingLimitType.WEEKLY,
                    amount=Decimal('2000.0000'),
                )
                GamblingLimit.objects.create(
                    user=user, limit_type=GamblingLimitType.MONTHLY,
                    amount=Decimal('5000.0000'),
                )
                # Fichas iniciales
                WalletService.deposit_tokens(
                    user, Decimal('500'), 'Fichas de bienvenida'
                )
                self.stdout.write(f'  Usuario creado: {username} (500 fichas)')

        # Admin
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                password='Admin1234!',
                email='admin@titanbet.com',
                dni='87654321',
                birth_date='1985-06-10',
            )
            self.stdout.write('  Superusuario creado: admin / Admin1234!')

        self.stdout.write(self.style.SUCCESS('\n✅ Seed completado correctamente.'))
        self.stdout.write(self.style.SUCCESS('   Usuarios: jugador1/jugador2/jugador3 (Test1234!)'))
        self.stdout.write(self.style.SUCCESS('   Admin: admin (Admin1234!)'))
