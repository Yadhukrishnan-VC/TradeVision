from __future__ import annotations

from rest_framework import serializers

from apps.risk_management.domain.value_objects import KillSwitchScope


class RiskDecisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    analysis_event_id = serializers.UUIDField()
    rule_id = serializers.CharField()
    symbol = serializers.CharField()
    event_type = serializers.CharField()
    status = serializers.CharField()
    rejection_code = serializers.CharField(allow_null=True, allow_blank=True)
    position_size = serializers.IntegerField()
    risk_amount = serializers.CharField(allow_null=True, allow_blank=True)
    risk_pct_of_capital = serializers.CharField(allow_null=True, allow_blank=True)
    risk_reward_ratio = serializers.CharField(allow_null=True, allow_blank=True)
    portfolio_gateway_impl = serializers.CharField()
    reason_message = serializers.CharField(allow_blank=True)
    trigger_data = serializers.JSONField()
    created_at = serializers.DateTimeField()


class KillSwitchToggleSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=[s.value for s in KillSwitchScope])
    symbol = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class KillSwitchStateSerializer(serializers.Serializer):
    scope = serializers.CharField()
    symbol = serializers.CharField(allow_null=True, allow_blank=True)
    is_active = serializers.BooleanField()
    actor = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    activated_at = serializers.DateTimeField()
    deactivated_at = serializers.DateTimeField(allow_null=True)
