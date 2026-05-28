import requests as http_requests
import json
from django.utils import timezone as tz
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.conf import settings
from decimal import Decimal

from .forms import RegistrationForm, SelfExclusionForm, GamblingLimitForm
from .models import AccountStatus, GamblingLimit, GamblingLimitType


@require_GET
def dni_lookup_view(request):
    """
    Proxy para consultar DNI contra APISPerú.
    El token se mantiene en el servidor; el browser nunca lo ve.
    """
    dni = request.GET.get('dni', '').strip()
    if len(dni) != 8 or not dni.isdigit():
        return JsonResponse({'error': 'DNI inválido. Debe tener exactamente 8 dígitos.'}, status=400)
    token = settings.APISPERU_TOKEN
    if not token:
        return JsonResponse({'error': 'Servicio de consulta DNI no configurado.'}, status=503)
    url = settings.APISPERU_DNI_URL.format(dni=dni)
    try:
        response = http_requests.get(url, params={'token': token}, timeout=8)
        data = response.json()
        if data.get('success') is True:
            return JsonResponse({
                'success': True,
                'nombres': data.get('nombres', ''),
                'apellido_paterno': data.get('apellidoPaterno', ''),
                'apellido_materno': data.get('apellidoMaterno', ''),
                'nombre_completo': (
                    f"{data.get('nombres', '')} "
                    f"{data.get('apellidoPaterno', '')} "
                    f"{data.get('apellidoMaterno', '')}"
                ).strip(),
            })
        else:
            msg = data.get('message', 'DNI no encontrado en RENIEC.')
            return JsonResponse({'error': msg}, status=404)
    except http_requests.Timeout:
        return JsonResponse({'error': 'Tiempo de espera agotado. Intenta de nuevo.'}, status=504)
    except http_requests.RequestException:
        return JsonResponse({'error': 'Error de conexión con el servicio DNI.'}, status=503)
    except Exception:
        return JsonResponse({'error': 'Respuesta inesperada del servicio DNI.'}, status=502)


def register_view(request):
    """Registro con KYC simulado (DNI + edad)."""
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.account_status = AccountStatus.VERIFIED
            user.save()
            GamblingLimit.objects.create(
                user=user, limit_type=GamblingLimitType.DAILY, amount=Decimal('500.0000'),
            )
            GamblingLimit.objects.create(
                user=user, limit_type=GamblingLimitType.WEEKLY, amount=Decimal('2000.0000'),
            )
            GamblingLimit.objects.create(
                user=user, limit_type=GamblingLimitType.MONTHLY, amount=Decimal('5000.0000'),
            )
            login(request, user)
            messages.success(request, '¡Registro exitoso! Tu cuenta ha sido verificada.')
            return redirect('betting:event_list')
    else:
        form = RegistrationForm()
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    """Inicio de sesión con registro de IP para anti-fraude."""
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            ip = request.META.get('REMOTE_ADDR')
            user.last_login_ip = ip
            user.save(update_fields=['last_login_ip'])
            login(request, user)
            messages.success(request, f'Bienvenido, {user.username}.')
            return redirect('betting:event_list')
    else:
        form = AuthenticationForm()
    return render(request, 'users/login.html', {'form': form})


def logout_view(request):
    """Cierre de sesión."""
    logout(request)
    messages.info(request, 'Has cerrado sesión.')
    return redirect('users:login')


@login_required
def profile_view(request):
    """Perfil del usuario con controles de juego responsable."""
    from apps.wallet.models import WalletService, LedgerEntry
    user = request.user
    balance = WalletService.get_balance(user)
    pending = WalletService.get_pending_balance(user)
    limits = list(user.limits.all())

    for limit in limits:
        limit.apply_pending_if_ready()

    transactions = LedgerEntry.objects.filter(
        user=user
    ).order_by('-created_at')[:10]

    limit_data = {}
    for l in limits:
        limit_data[l.limit_type] = {
            'amount': l.amount,
            'pending_amount': l.pending_amount,
            'pending_effective_at': l.pending_effective_at,
        }

    return render(request, 'users/profile.html', {
        'balance': balance,
        'pending': pending,
        'limits': limits,
        'limit_data': limit_data,
        'transactions': transactions,
        'is_self_excluded': (
            user.self_excluded_permanent or
            (user.self_excluded_until and tz.now() < user.self_excluded_until)
        ),
    })


@login_required
def self_exclusion_view(request):
    """Autoexclusión: temporal (7/30/90 días) o permanente."""
    if request.method == 'POST':
        form = SelfExclusionForm(request.POST)
        if form.is_valid():
            days = form.get_days()
            request.user.apply_self_exclusion(days)
            if days is None:
                messages.warning(request, 'Te has autoexcluido de forma permanente.')
            else:
                messages.warning(request, f'Te has autoexcluido por {days} días.')
            return redirect('users:profile')
    else:
        form = SelfExclusionForm()
    return render(request, 'users/self_exclusion.html', {'form': form})


@login_required
def update_limits_view(request):
    """Actualizar límites de depósito (diario, semanal, mensual)."""
    if request.method == 'POST':
        form = GamblingLimitForm(request.POST)
        if form.is_valid():
            type_map = {
                'daily': GamblingLimitType.DAILY,
                'weekly': GamblingLimitType.WEEKLY,
                'monthly': GamblingLimitType.MONTHLY,
            }
            for field_name, limit_type in type_map.items():
                new_amount = form.cleaned_data.get(field_name)
                if new_amount is not None:
                    limit, _ = GamblingLimit.objects.get_or_create(
                        user=request.user, limit_type=limit_type,
                        defaults={'amount': new_amount},
                    )
                    if not _:
                        old = limit.amount
                        limit.update_limit(new_amount)
                        if new_amount > old:
                            messages.info(
                                request,
                                f'Límite {limit.get_limit_type_display()} se '
                                f'actualizará a {new_amount} en 24 horas.'
                            )
                        else:
                            messages.success(
                                request,
                                f'Límite {limit.get_limit_type_display()} '
                                f'actualizado a {new_amount}.'
                            )
            return redirect('users:profile')
    else:
        limits = {}
        for limit in request.user.limits.all():
            limits[limit.limit_type] = limit.amount
        form = GamblingLimitForm(initial={
            'daily': limits.get(GamblingLimitType.DAILY, Decimal('500')),
            'weekly': limits.get(GamblingLimitType.WEEKLY, Decimal('2000')),
            'monthly': limits.get(GamblingLimitType.MONTHLY, Decimal('5000')),
        })
    return render(request, 'users/update_limits.html', {'form': form})
