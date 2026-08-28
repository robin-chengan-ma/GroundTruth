from rest_framework import viewsets

from api.core.permissions import IsBusinessAdmin
from lib.jwt_authentication import BusinessJwtAuthentication
from repositories.core import RoleRepository, UserRepository
from schemas.core import RoleSerializer, UserSerializer


class RoleViewSet(viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [IsBusinessAdmin]

    def get_queryset(self):
        return RoleRepository.all()


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    authentication_classes = [BusinessJwtAuthentication]
    permission_classes = [IsBusinessAdmin]

    def get_queryset(self):
        return UserRepository.all()
