from rest_framework import serializers

from apps.core.models import Role, User


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "role", "approval_amount_limit"]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "password", "role", "created_at"]
        extra_kwargs = {
            "password": {"write_only": True},
        }
