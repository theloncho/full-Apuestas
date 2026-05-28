from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from decimal import Decimal

from .forms import RegistrationForm, SelfExclusionForm, GamblingLimitForm
from .models import AccountStatus, GamblingLimit, GamblingLimitType


def register_view(request):
    """Registro con KYC simulado (DNI + edad)."""
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.account_status = AccountStatus.VERIFIED
            user.save()
            # Crear límites por defecto
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
            login(request, user)
            messages.success(request, '¡Registro exitoso! Tu cuenta ha sido verificada.')
            return redirect('betting:event_list')
    else:
        form = RegistrationForm()
    return render(request, 'users/register.html', {'form': form})


def login_view(request):
    """Inicio de sesión."""
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            # Registrar IP para anti-fraude
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
    from apps.wallet.models import WalletService
    user = request.user
    balance = WalletService.get_balance(user)
    pending = WalletService.get_pending_balance(user)
    limits = user.limits.all()

    # Aplicar límites pendientes si corresponde
    for limit in limits:
        limit.apply_pending_if_ready()

    return render(request, 'users/profile.html', {
        'balance': balance,
        'pending': pending,
        'limits': limits,
    })


@login_required
def self_exclusion_view(request):
    """Autoexclusión: temporal o permanente."""
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
    """Actualizar límites de depósito."""
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
