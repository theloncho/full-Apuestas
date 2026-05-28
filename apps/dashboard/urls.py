from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('export/mincetur/', views.export_mincetur_report, name='export_mincetur'),
    path('audit/verify/', views.verify_audit_chain, name='verify_audit'),
    path('liquidate/<int:event_id>/', views.liquidate_event_view, name='liquidate_event'),
    path('fraud/', views.fraud_alerts_view, name='fraud_alerts'),
]
