"""
Cliente para The Odds API v4.
Encapsula toda la comunicación HTTP con la API externa.
Documentación: https://the-odds-api.com/liveapi/guides/v4/
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Timeout generoso para evitar bloqueos en Celery
REQUEST_TIMEOUT = 15  # segundos


class OddsAPIError(Exception):
    """Error genérico de la API."""
    pass


class QuotaExhaustedError(OddsAPIError):
    """Se agotó la cuota mensual."""
    pass


class OddsAPIClient:
    """
    Cliente HTTP para The Odds API v4.

    Uso:
        client = OddsAPIClient()
        sports = client.fetch_sports()
        odds = client.fetch_odds('soccer')
    """

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or getattr(settings, 'ODDS_API_KEY', '')
        self.base_url = base_url or getattr(
            settings, 'ODDS_API_BASE_URL', 'https://api.the-odds-api.com/v4'
        )
        if not self.api_key:
            raise OddsAPIError(
                "ODDS_API_KEY no configurada. "
                "Agrégala en settings o como variable de entorno."
            )

    # ─── Endpoints ────────────────────────────────────────────────────────

    def fetch_sports(self) -> list[dict]:
        """
        Lista de deportes activos.
        NO consume cuota de la API.
        """
        url = f'{self.base_url}/sports/'
        return self._get(url)

    def fetch_odds(
        self,
        sport_key: str = None,
        regions: str = None,
        markets: str = None,
    ) -> list[dict]:
        """
        Cuotas actuales para un deporte.
        Costo: 1 crédito por región por mercado.

        Args:
            sport_key: Clave del deporte (ej. 'soccer', 'soccer_spain_la_liga')
            regions: Región de casas de apuestas (ej. 'eu', 'us')
            markets: Mercados (ej. 'h2h', 'h2h,totals')

        Returns:
            Lista de eventos con sus cuotas de distintas casas
        """
        sport = sport_key or getattr(settings, 'ODDS_API_SPORT', 'soccer')
        url = f'{self.base_url}/sports/{sport}/odds/'
        params = {
            'regions': regions or getattr(settings, 'ODDS_API_REGIONS', 'eu'),
            'markets': markets or getattr(settings, 'ODDS_API_MARKETS', 'h2h,totals'),
            'oddsFormat': 'decimal',
            'dateFormat': 'iso',
        }
        return self._get(url, params=params)

    def fetch_scores(
        self,
        sport_key: str = None,
        days_from: int = None,
    ) -> list[dict]:
        """
        Marcadores en vivo y recientes.
        Costo: 1 crédito (sin daysFrom), 2 créditos (con daysFrom).

        Args:
            sport_key: Clave del deporte
            days_from: Días hacia atrás (1-3) para incluir partidos completados

        Returns:
            Lista de eventos con marcadores
        """
        sport = sport_key or getattr(settings, 'ODDS_API_SPORT', 'soccer')
        url = f'{self.base_url}/sports/{sport}/scores/'
        params = {}
        if days_from is not None:
            params['daysFrom'] = min(max(days_from, 1), 3)
        params['dateFormat'] = 'iso'
        return self._get(url, params=params)

    # ─── HTTP interno ─────────────────────────────────────────────────────

    def _get(self, url: str, params: dict = None) -> list | dict:
        """Ejecuta un GET autenticado con manejo robusto de errores."""
        if params is None:
            params = {}
        params['apiKey'] = self.api_key

        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            logger.error('odds_api_timeout', extra={'url': url})
            raise OddsAPIError(f'Timeout al conectar con The Odds API: {url}')
        except requests.exceptions.ConnectionError:
            logger.error('odds_api_connection_error', extra={'url': url})
            raise OddsAPIError(f'Error de conexión con The Odds API: {url}')

        # Loguear cuota
        remaining = response.headers.get('x-requests-remaining', '?')
        used = response.headers.get('x-requests-used', '?')
        last_cost = response.headers.get('x-requests-last', '?')
        logger.info(
            'odds_api_call',
            extra={
                'url': url,
                'status': response.status_code,
                'quota_remaining': remaining,
                'quota_used': used,
                'last_cost': last_cost,
            },
        )

        if response.status_code == 429:
            raise QuotaExhaustedError(
                f'Cuota agotada. Restante: {remaining}, Usado: {used}'
            )

        if response.status_code == 401:
            raise OddsAPIError('API key inválida o expirada.')

        if response.status_code != 200:
            raise OddsAPIError(
                f'Error HTTP {response.status_code}: {response.text[:200]}'
            )

        return response.json()

    # ─── Mapeo a modelos internos ─────────────────────────────────────────

    @staticmethod
    def extract_best_odds(event_data: dict, market_key: str = 'h2h') -> dict:
        """
        De un evento de la API, extrae las mejores cuotas disponibles
        promediando entre todas las casas de apuestas.

        Args:
            event_data: Un elemento de la respuesta de fetch_odds
            market_key: 'h2h' para 1X2, 'totals' para Over/Under

        Returns:
            Dict con nombre de selección → cuota Decimal promedio.
            Ej: {'1': Decimal('2.35'), 'X': Decimal('3.40'), '2': Decimal('2.90')}
        """
        odds_by_outcome: dict[str, list[Decimal]] = {}

        for bookmaker in event_data.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                if market.get('key') != market_key:
                    continue
                for outcome in market.get('outcomes', []):
                    name = outcome.get('name', '')
                    try:
                        price = Decimal(str(outcome['price']))
                    except (KeyError, ValueError, TypeError):
                        continue
                    odds_by_outcome.setdefault(name, []).append(price)

        # Promediar cuotas de todas las casas
        result = {}
        for name, prices in odds_by_outcome.items():
            avg = sum(prices) / len(prices)
            result[name] = avg.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

        return result

    @staticmethod
    def map_outcome_to_selection(outcome_name: str, home_team: str, away_team: str) -> Optional[str]:
        """
        Mapea el nombre de un outcome de la API a nuestro nombre de selección interno.

        La API usa nombres de equipos (ej. 'Tampa Bay Buccaneers').
        Nosotros usamos '1', 'X', '2'.

        Returns:
            '1' si es el home_team, '2' si es el away_team, 'X' si es 'Draw', None si no mapea.
        """
        name_lower = outcome_name.lower().strip()
        home_lower = home_team.lower().strip()
        away_lower = away_team.lower().strip()

        if name_lower == home_lower or name_lower == 'home':
            return '1'
        elif name_lower == away_lower or name_lower == 'away':
            return '2'
        elif name_lower in ('draw', 'empate', 'x'):
            return 'X'
        elif 'over' in name_lower:
            return f'Over {name_lower.split("over")[-1].strip()}'
        elif 'under' in name_lower:
            return f'Under {name_lower.split("under")[-1].strip()}'
        return None
