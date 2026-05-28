from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from decimal import Decimal, InvalidOperation

from .models import WalletService, LedgerEntry


class DepositSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal('0.0001'))
    idempotency_key = serializers.UUIDField(required=False)


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ['id', 'account_type', 'amount', 'direction', 'transaction_id', 'description', 'created_at']


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_balance(request):
    balance = WalletService.get_balance(request.user)
    pending = WalletService.get_pending_balance(request.user)
    return Response({
        'balance': str(balance),
        'pending': str(pending),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_deposit(request):
    serializer = DepositSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        tx_id = WalletService.deposit_tokens(
            request.user, serializer.validated_data['amount']
        )
        return Response({
            'transaction_id': str(tx_id),
            'balance': str(WalletService.get_balance(request.user)),
        }, status=status.HTTP_201_CREATED)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_transactions(request):
    entries = LedgerEntry.objects.filter(user=request.user).order_by('-created_at')[:50]
    serializer = LedgerEntrySerializer(entries, many=True)
    return Response(serializer.data)


app_name = 'wallet-api'

from django.urls import path
urlpatterns = [
    path('balance/', api_balance, name='balance'),
    path('deposit/', api_deposit, name='deposit'),
    path('transactions/', api_transactions, name='transactions'),
]
