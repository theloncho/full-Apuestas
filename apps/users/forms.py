from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from .validators import validate_age, validate_dni


class RegistrationForm(UserCreationForm):
    """Formulario de registro con KYC simulado."""
    dni = forms.CharField(
        max_length=8, min_length=8,
        label='DNI',
        help_text='Ingresa tu DNI peruano de 8 dígitos.',
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': '12345678',
            'pattern': '[0-9]{8}', 'maxlength': '8',
        }),
    )
    birth_date = forms.DateField(
        label='Fecha de nacimiento',
        widget=forms.DateInput(attrs={
            'class': 'form-control', 'type': 'date',
        }),
    )
    phone = forms.CharField(
        max_length=20, required=False,
        label='Teléfono',
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': '999888777',
        }),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'dni', 'birth_date', 'phone', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def clean_dni(self):
        dni = self.cleaned_data.get('dni')
        validate_dni(dni)
        return dni

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get('birth_date')
        validate_age(birth_date)
        return birth_date


class SelfExclusionForm(forms.Form):
    """Formulario de autoexclusión."""
    EXCLUSION_CHOICES = [
        (7, '7 días'),
        (30, '30 días'),
        (90, '90 días'),
        (0, 'Indefinida (permanente)'),
    ]
    duration = forms.ChoiceField(
        choices=EXCLUSION_CHOICES,
        label='Duración de la autoexclusión',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
    )

    def get_days(self) -> int | None:
        duration = int(self.cleaned_data['duration'])
        return None if duration == 0 else duration


class GamblingLimitForm(forms.Form):
    """Formulario para configurar límites de depósito."""
    daily = forms.DecimalField(
        max_digits=18, decimal_places=4,
        min_value=0, required=False,
        label='Límite diario',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
    )
    weekly = forms.DecimalField(
        max_digits=18, decimal_places=4,
        min_value=0, required=False,
        label='Límite semanal',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
    )
    monthly = forms.DecimalField(
        max_digits=18, decimal_places=4,
        min_value=0, required=False,
        label='Límite mensual',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1'}),
    )
