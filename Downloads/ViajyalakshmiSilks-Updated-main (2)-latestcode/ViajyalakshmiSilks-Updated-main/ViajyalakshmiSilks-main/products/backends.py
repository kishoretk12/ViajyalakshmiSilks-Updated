from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q
from .models import UserProfile

class EmailOrMobileBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get('username')
        
        try:
            # Check if the username matches an email in User model
            # or a mobile_number in UserProfile
            user = User.objects.get(
                Q(email__iexact=username) | Q(userprofile__mobile_number=username)
            )
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # If multiple are returned (shouldn't happen with unique emails/mobile numbers),
            # try to match exactly
            return User.objects.filter(email__iexact=username).order_by('id').first()

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
