from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.encoding import smart_text
from django.utils.translation import ugettext as _
from rest_framework import exceptions
from rest_framework.authentication import (
    BaseAuthentication, get_authorization_header
)

import firebase_admin
from firebase_admin import auth, credentials


User = get_user_model()

cred = credentials.Certificate(settings.FIREBASE_APP_CREDENTIALS)
firebase_admin.initialize_app(cred)


class FirebaseAuthentication(BaseAuthentication):
    """
    Token based authentication using firebase.
    
    Clients should authenticate by passing a Firebase ID token in the 
    Authorizaiton header using Bearer scheme.
    """
    www_authenticate_realm = 'api'
    auth_header_prefix = 'Bearer'
    uid_field = 'username' 

    def authenticate(self, request):
        """
        Returns a two-tuple of `User` and decoded firebase payload if a valid signature 
        has been supplied.
        """
        firebase_token = self.get_token(request)

        try:
            payload = auth.verify_id_token(firebase_token)
        except ValueError:
            msg = _('Invalid token.')
            raise exceptions.AuthenticationFailed(msg)
        except (auth.ExpiredIdTokenError, auth.InvalidIdTokenError, auth.RevokedIdTokenError):
            msg = _('Could not log in.')
            raise exceptions.AuthenticationFailed(msg)

        user = self.authenticate_credentials(payload)

        return (user, payload)

    def get_token(self, request):
        """
        Returns the firebase ID token from request.
        """
        auth = get_authorization_header(request).split()

        if not auth:
            return None

        if len(auth) == 1:
            msg = _('Invalid Authorization header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid Authorization header. Credentials string should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)

        if smart_text(auth[0].lower()) != self.auth_header_prefix.lower():
            return None

        return auth[1]

    def authenticate_credentials(self, payload):
        """
        Returns an user that matches the payload's user uid and email.
        """
        if payload['firebase']['sign_in_provider'] == 'anonymous':
            msg = _('Firebase anonymous sign-in is not supported.')
            raise exceptions.AuthenticationFailed(msg)

        uid = payload['uid']

        if settings.FIREBASE_EMAIL_VERIFICATION:
            if not payload['email_verified']:
                msg = _('User email not yet confirmed.')
                raise exceptions.AuthenticationFailed(msg)
            
        try:
            user = User.objects.get(**{self.uid_field: uid})
        except User.DoesNotExist:
            firebase_user = auth.get_user(uid)
            user = self.create_user_from_firebase(uid, firebase_user)

        return user

    def create_user_from_firebase(self, uid: str, firebase_user: auth.UserRecord) -> User:
        """Creates a new user with firebase info"""
        fields = {
            self.uid_field: uid,
            'email': firebase_user.email
        }

        return User.objects.create(**fields)

    def authenticate_header(self, request):
        return f'{self.auth_header_prefix} realm="{self.www_authenticate_realm}"'
