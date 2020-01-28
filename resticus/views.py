import yaml

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, StreamingHttpResponse, Http404

from django.utils.decorators import method_decorator
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from . import exceptions, http
from .auth import SessionAuth, TokenAuth
from .compat import get_user_model
from .parsers import parse_content_type
from .permissions import AllowAny
from .schemas import SchemaGenerator
from .serializers import serialize
from .settings import api_settings

__all__ = ['Endpoint', 'SessionAuthEndpoint', 'TokenAuthEndpoint']


class Endpoint(View):
    """
    Class-based Django view that should be extended to provide an API
    endpoint (resource). To provide GET, POST, PUT, HEAD or DELETE methods,
    implement the corresponding get(), post(), put(), head() or delete()
    method, respectively.

    If you also implement authenticate(request) method, it will be called
    before the main method to provide authentication, if needed. Auth mixins
    use this to provide authentication.

    The usual Django "request" object passed to methods is extended with a
    few more attributes:

      * request.content_type - the content type of the request
      * request.params - a dictionary with GET parameters
      * request.data - a dictionary with POST/PUT parameters, as parsed from
          either form submission or submitted application/json data payload
      * request.raw_data - string containing raw request body

    The view method should return either a HTTPResponse (for example, a
    redirect), or something else (usually a dictionary or a list). If something
    other than HTTPResponse is returned, it is first serialized into
    :py:class:`resticus.http.JSONResponse` with a status code 200 (OK),
    then returned.

    The authenticate method should return either a HttpResponse, which will
    shortcut the rest of the request handling (the view method will not be
    called), or None (the request will be processed normally).

    Both methods can raise a :py:class:`resticus.http.HttpError` exception
    instead of returning a HttpResponse, to shortcut the request handling and
    immediately return the error to the client.
    """

    authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    login_required = api_settings.LOGIN_REQUIRED
    permission_classes = api_settings.DEFAULT_PERMISSION_CLASSES
    data_parsers = api_settings.DATA_PARSERS

    streaming = False

    def parse_body(self, request):
        if request.method not in ['POST', 'PUT', 'PATCH']:
            return (None, None)

        content_type, params = parse_content_type(request.content_type)

        try:
            parser = self.data_parsers[content_type]
        except KeyError:
            raise exceptions.ParseError()

        return parser(request, **params)

    def authenticate(self, request):
        request.authenticator = None

        try:
            if request.user.is_authenticated:
                return request.user
        except AttributeError:
            pass

        for authenticator in self.get_authenticators():
            user = authenticator.authenticate(request)
            if user and user.is_authenticated:
                request.authenticator = authenticator
                return user

        # User is not authenticated, so short circuit if login_required.
        handler = getattr(self, request.method.lower(), None)
        if getattr(handler, 'login_required', self.login_required):
            msg = _('You must be logged in to access this endpoint.')
            raise exceptions.AuthenticationFailed(msg)

        return AnonymousUser()

    def get_authenticators(self):
        """
        Instantiates and returns the list of authenticators that this view can use.
        """
        return [auth() for auth in self.authentication_classes]

    def get_authenticate_header(self, request):
        """
        If a request is unauthenticated, determine the WWW-Authenticate
        header to use for 401 responses, if any.
        """
        authenticators = self.get_authenticators()
        if authenticators:
            return authenticators[0].authenticate_header(request)

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        return [permission() for permission in self.permission_classes]

    def check_permissions(self, request):
        """
        Check if the request should be permitted.
        Raises an appropriate exception if the request is not permitted.
        """
        for permission in self.get_permissions():
            if not permission.has_permission(request, self):
                self.permission_denied(request)

    def check_object_permissions(self, request, obj):
        """
        Check if the request should be permitted for a given object.
        Raises an appropriate exception if the request is not permitted.
        """
        for perm in self.get_permissions():
            if not perm.has_object_permission(request, self, obj):
                self.permission_denied(request)

    def permission_denied(self, request):
        """
        If request is not permitted, determine what kind of exception to raise.
        """
        if not request.authenticator:
            raise exceptions.NotAuthenticated()
        raise exceptions.PermissionDenied()

    def http_method_not_allowed(self, request, *args, **kwargs):
        return http.Http405(request.method, permitted_methods=self._allowed_methods())

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        request.params = dict((k, v) for (k, v) in request.GET.items())
        request.data = None
        request.files = None
        request.raw_data = request.body

        try:
            request.user = self.authenticate(request)
            self.check_permissions(request)
            request.data, request.files = self.parse_body(request)
            response = super(Endpoint, self).dispatch(request, *args, **kwargs)

        except Http404:
            return http.Http404()

        except exceptions.AuthenticationFailed as err:
            response = self.authentication_failed(err)

        except ValidationError as err:
            return http.Http400(err.message)

        except exceptions.APIException as err:
            response = self.api_exception(err)

        except Exception as err:
            response = self.server_error(err)

        if not isinstance(response, (HttpResponse, StreamingHttpResponse)):
            if self.streaming:
                response = self.streaming_response(response)
            else:
                response = http.Http200(response)
        return response

    def authentication_failed(self, err):
        # WWW-Authenticate header for 401 responses, else coerce to 403
        auth_header = self.get_authenticate_header(self.request)
        if auth_header:
            err.response['WWW-Authenticate'] = auth_header
        else:
            err.response.status_code = 403
        return err.response

    def server_error(self, err):
        if settings.DEBUG:
            return http.Http500(str(err))
        return http.Http500(_('Internal server error.'))

    def api_exception(self, err):
        return err.response

    def streaming_response(self, data, **kwargs):
        kwargs.setdefault('status', 200)
        return http.StreamingJSONResponse(data, **kwargs)


class SessionAuthEndpoint(Endpoint):
    """
    Session-based authentication API endpoint. Provides a GET method for
    authenticating the user based on passed-in "username" and "password"
    request params. On successful authentication, the method returns
    authenticated user details.

    Uses :py:class:`UsernamePasswordAuthMixin` to actually implement the
    Authentication API endpoint.

    On success, the user will get a response with their serialized User
    object, containing id, username, first_name, last_name and email fields.
    """

    authentication_classes = (SessionAuth,)

    permission_classes = ()

    login_required = False

    user_fields = ('id', 'username', 'first_name', 'last_name', 'email')

    def get(self, request, **kwargs):
        return http.Http200({
            'data': serialize(request.user, fields=self.user_fields)
        })

    get.login_required = True

    def post(self, request, **kwargs):
        credentials = self.get_credentials(request)
        request.user = auth.authenticate(request, **credentials)

        if request.user is None:
            raise exceptions.AuthenticationFailed(_('Invalid username/password.'))

        if not request.user.is_active:
            raise exceptions.AuthenticationFailed(_('User inactive or deleted.'))

        auth.login(request, request.user)
        return self.get(request)

    def get_credentials(self, request):
        username_field = getattr(get_user_model(), 'USERNAME_FIELD', 'username')

        username = request.data.get(username_field,
            request.data.get('username'))
        password = request.data.get('password')

        return {
            username_field: username,
            'password': password
        }


class TokenAuthEndpoint(Endpoint):
    authentication_classes = (TokenAuth,)

    permission_classes = ()

    login_required = False

    user_fields = ('id', 'username', 'first_name', 'last_name', 'email')

    def get(self, request, **kwargs):
        data = serialize(request.user, fields=self.user_fields)
        data['api_token'] = self.get_token(request).key
        return http.Http200({'data': data})

    get.login_required = True

    def post(self, request, **kwargs):
        credentials = self.get_credentials(request)
        request.user = auth.authenticate(request, **credentials)

        if request.user is None:
            raise exceptions.AuthenticationFailed(_('Invalid username/password.'))

        if not request.user.is_active:
            raise exceptions.AuthenticationFailed(_('User inactive or deleted.'))

        return self.get(request)

    def get_credentials(self, request):
        username_field = getattr(get_user_model(), 'USERNAME_FIELD', 'username')

        username = request.data.get(username_field,
            request.data.get('username'))
        password = request.data.get('password')

        return {
            username_field: username,
            'password': password
        }

    def get_token(self, request):
        TokenModel = TokenAuth.get_token_model()
        token, created = TokenModel.objects.get_or_create(user=request.user)
        return token


def get_schema_view(title=None, urlconf=None, prefix=None):
    """
    Returns a Swagger/OpenAPI schema
    """
    class SchemaView(Endpoint):
        exclude_from_schema = True
        permission_classes = [AllowAny]

        def get(self, request):
            generator = SchemaGenerator(
                title=title,
                urlconf=urlconf,
                prefix=prefix
            )
            schema = generator.get_schema(request=request)
            schema = yaml.dump(schema, allow_unicode=True)

            if not schema:
                raise exceptions.ValidationError('Schema could not be generated.')

            return HttpResponse(schema)

    return SchemaView.as_view()
