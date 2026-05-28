"""
Tests de auditoría — cadena de hash inmutable.
"""
import pytest
from apps.audit.models import AuditLog


@pytest.mark.django_db
class TestAuditChain:
    def test_chain_integrity_empty(self):
        result = AuditLog.verify_chain_integrity()
        assert result['valid'] is True

    def test_chain_integrity_with_entries(self, verified_user):
        AuditLog.log('test_event_1', {'key': 'value1'}, verified_user)
        AuditLog.log('test_event_2', {'key': 'value2'}, verified_user)
        AuditLog.log('test_event_3', {'key': 'value3'})

        result = AuditLog.verify_chain_integrity()
        assert result['valid'] is True
        assert result['total_entries'] == 3

    def test_chain_links_properly(self, verified_user):
        log1 = AuditLog.log('event_a', {'data': 1})
        log2 = AuditLog.log('event_b', {'data': 2})

        assert log2.previous_hash == log1.chain_hash
        assert log1.previous_hash == '0' * 64
