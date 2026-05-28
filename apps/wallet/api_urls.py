from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from decimal import Decimal, InvalidOperation

from .models import WalletService, LedgerEntry


from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

class DepositSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal('0.0001'))
    idempotency_key = serializers.UUIDField(required=False)


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ['id', 'account_type', 'amount', 'direction', 'transaction_id', 'description', 'created_at']


class BalanceResponseSerializer(serializers.Serializer):
    balance = serializers.CharField()
    pending = serializers.CharField()

@extend_schema(
    responses=BalanceResponseSerializer,
    description="Get current wallet balance and pending locked funds.",
    tags=['Wallet']
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_balance(request):
    balance = WalletService.get_balance(request.user)
    pending = WalletService.get_pending_balance(request.user)
    return Response({
        'balance': str(balance),
        'pending': str(pending),
    })


class DepositResponseSerializer(serializers.Serializer):
    transaction_id = serializers.UUIDField()
    balance = serializers.CharField()

@extend_schema(
    request=DepositSerializer,
    responses={
        201: DepositResponseSerializer,
        400: OpenApiTypes.OBJECT,
    },
    description="Deposit virtual tokens into user's wallet.",
    tags=['Wallet']
)
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


@extend_schema(
    responses=LedgerEntrySerializer(many=True),
    description="Get the recent ledger entry transactions for the authenticated user.",
    tags=['Wallet']
)
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
