from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # 'username' argument might actually be the email address
        # Check if the user exists with this email
        try:
            user = User.objects.get(Q(email__iexact=username) | Q(username__iexact=username))
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # If there are multiple users with the same email, get the first one
            user = User.objects.filter(Q(email__iexact=username) | Q(username__iexact=username)).order_by('id').first()
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        return None
