"""
Management command para sincronizar cuotas desde The Odds API bajo demanda.

Uso:
    python manage.py fetch_odds
    python manage.py fetch_odds --sport soccer_spain_la_liga
    python manage.py fetch_odds --scores
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sincroniza cuotas (odds) en tiempo real desde The Odds API v4'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sport',
            type=str,
            default=None,
            help='Sport key (ej. soccer, soccer_spain_la_liga). Default: settings.ODDS_API_SPORT',
        )
        parser.add_argument(
            '--scores',
            action='store_true',
            help='También sincronizar marcadores en vivo',
        )
        parser.add_argument(
            '--list-sports',
            action='store_true',
            help='Listar deportes disponibles en la API (no consume cuota)',
        )

    def handle(self, *args, **options):
        from apps.odds.odds_api_client import OddsAPIClient, OddsAPIError

        try:
            client = OddsAPIClient()
        except OddsAPIError as e:
            self.stderr.write(self.style.ERROR(f'❌ {e}'))
            return

        # ─── Listar deportes ──────────────────────────────────────────────
        if options['list_sports']:
            self.stdout.write('📋 Deportes disponibles en The Odds API:\n')
            try:
                sports = client.fetch_sports()
                for sport in sports:
                    active = '✅' if sport.get('active') else '❌'
                    self.stdout.write(
                        f"  {active} {sport['key']:40s} "
                        f"{sport.get('title', '')} ({sport.get('group', '')})"
                    )
                self.stdout.write(f'\n  Total: {len(sports)} deportes')
            except OddsAPIError as e:
                self.stderr.write(self.style.ERROR(f'❌ Error: {e}'))
            return

        # ─── Sync odds ────────────────────────────────────────────────────
        self.stdout.write('🔄 Sincronizando cuotas desde The Odds API...\n')

        from apps.odds.tasks import fetch_and_sync_odds
        result = fetch_and_sync_odds()

        if result.get('status') == 'success':
            self.stdout.write(self.style.SUCCESS(
                f"✅ Sincronización completada:\n"
                f"   Eventos importados: {result.get('events_created', 0)}\n"
                f"   Eventos actualizados: {result.get('events_matched', 0)}\n"
                f"   Cuotas cambiadas: {result.get('odds_changed', 0)}"
            ))
        elif result.get('status') == 'quota_exhausted':
            self.stderr.write(self.style.WARNING(
                f"⚠️  Cuota agotada: {result.get('detail', '')}"
            ))
        elif result.get('status') == 'no_events':
            self.stdout.write(self.style.WARNING(
                '⚠️  La API no retornó eventos para este deporte.'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"ℹ️  {result.get('status', 'unknown')}: {result.get('reason', '')}"
            ))

        # ─── Sync scores (opcional) ───────────────────────────────────────
        if options['scores']:
            self.stdout.write('\n🏟️  Sincronizando marcadores en vivo...\n')
            from apps.odds.tasks import sync_live_scores
            score_result = sync_live_scores()

            if score_result.get('status') == 'success':
                self.stdout.write(self.style.SUCCESS(
                    f"✅ Marcadores actualizados: {score_result.get('scores_updated', 0)}"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"ℹ️  {score_result.get('status', 'unknown')}: "
                    f"{score_result.get('reason', '')}"
                ))

        self.stdout.write('')
