from django.contrib import admin
from .models import Sport, Event, Market, Selection, Bet, CombinedBet
from .services import LiquidationService


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')


class MarketInline(admin.TabularInline):
    model = Market
    extra = 0


class SelectionInline(admin.TabularInline):
    model = Selection
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('home_team', 'away_team', 'scheduled_at', 'status', 'result_home', 'result_away')
    list_filter = ('status', 'sport', 'scheduled_at')
    search_fields = ('home_team', 'away_team')
    inlines = [MarketInline]
    actions = ['mark_live', 'mark_suspended']

    @admin.action(description='Marcar como en vivo')
    def mark_live(self, request, queryset):
        queryset.filter(status='programado').update(status='en_vivo')

    @admin.action(description='Suspender evento')
    def mark_suspended(self, request, queryset):
        queryset.update(status='suspendido')


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ('event', 'market_type', 'is_suspended', 'line')
    list_filter = ('market_type', 'is_suspended')
    inlines = [SelectionInline]


@admin.register(Selection)
class SelectionAdmin(admin.ModelAdmin):
    list_display = ('market', 'name', 'odds', 'is_winner')
    list_filter = ('is_winner',)


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'selection', 'stake', 'odds_at_placement', 'status', 'payout', 'placed_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'id')
    readonly_fields = ('id', 'placed_at', 'settled_at')


@admin.register(CombinedBet)
class CombinedBetAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'stake', 'combined_odds', 'status', 'payout')
    list_filter = ('status',)
