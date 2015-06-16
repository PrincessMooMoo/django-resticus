import base64

from restless.auth import login_required, BasicHttpAuth
from restless.exceptions import HttpError
from restless.http import Http201, Http403, Http404, Http400
from restless.models import serialize
from restless.modelviews import ListEndpoint, DetailEndpoint, ActionEndpoint
from restless.views import Endpoint

from .models import *
from .forms import *

__all__ = ['AuthorList', 'AuthorDetail', 'PublisherList', 'PublisherDetail',
    'ReadOnlyPublisherList', 'PublisherAction', 'BookDetail',
    'FailsIntentionally', 'WildcardHandler', 'EchoView', 'ErrorRaisingView',
    'BasicAuthEndpoint']


class AuthorList(Endpoint):
    def get(self, request):
        return serialize(Author.objects.all())

    def post(self, request):
        form = AuthorForm(request.data)
        if form.is_valid():
            author = form.save()
            return Http201(serialize(author))
        else:
            return Http400(reason='invalid author data',
                details=form.errors)


class AuthorDetail(Endpoint):
    def get(self, request, author_id=None):
        author_id = int(author_id)
        try:
            return serialize(Author.objects.get(id=author_id))
        except Author.DoesNotExist:
            return Http404(reason='no such author')

    def delete(self, request, author_id=None):
        author_id = int(author_id)
        Author.objects.get(id=author_id).delete()
        return 'ok'

    def put(self, request, author_id=None):
        author_id = int(author_id)
        try:
            author = Author.objects.get(id=author_id)
        except Author.DoesNotExist:
            return Http404(reason='no such author')

        form = AuthorForm(request.data, instance=author)
        if form.is_valid():
            author = form.save()
            return serialize(author)
        else:
            return Http400(reason='invalid author data',
                details=form.errors)


class PublisherList(ListEndpoint):
    model = Publisher


class PublisherDetail(DetailEndpoint):
    model = Publisher


class ReadOnlyPublisherList(ListEndpoint):
    model = Publisher
    methods = ['GET']


class PublisherAction(ActionEndpoint):
    model = Publisher

    def action(self, obj, *args, **kwargs):
        return {'result': 'done'}


class BookDetail(DetailEndpoint):
    model = Book
    lookup_field = 'isbn'


class FailsIntentionally(Endpoint):
    def get(self, request):
        raise Exception("I'm being a bad view")


class WildcardHandler(Endpoint):
    def dispatch(self, request, *args, **kwargs):
        return Http404('no such resource: %s %s' % (
            request.method, request.path))


class EchoView(Endpoint):
    def post(self, request):
        return {
            'headers': dict((k, str(v)) for k, v in request.META.items()),
            'raw_data': base64.b64encode(request.raw_data).decode('ascii')
        }

    def get(self, request):
        return self.post(request)

    def put(self, request):
        return self.post(request)


class ErrorRaisingView(Endpoint):
    def get(self, request):
        raise HttpError(400, 'raised error')


class BasicAuthEndpoint(Endpoint):
    authentication_classes = (BasicHttpAuth,)

    @login_required
    def get(self, request):
        return serialize(request.user)
