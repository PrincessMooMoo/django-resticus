import warnings

from django.core.serializers.json import DjangoJSONEncoder
from django.utils.encoding import force_text
from django.utils.functional import Promise

from .compat import json


class JSONDecoder(json.JSONDecoder):
    pass


class JSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        # Handle strings marked for translation
        if isinstance(obj, Promise):
            return force_text(obj)
        return super(JSONEncoder, self).default(obj)


class RapidJSONDecoder(object):
    def decode(self, data):
        import rapidjson
        return rapidjson.loads(data, use_decimal=True)


class RapidJSONEncoder(object):
    def __init__(self):
        self._encoder = JSONEncoder()

    def encode(self, data):
        import rapidjson
        return rapidjson.dumps(data, default=self._encoder.default,
            use_decimal=True, datetime_mode=True)

    def iterencode(self, data):
        warnings.warn('iterencode is not available in rapidjson, defaulting to json.')
        return self._encoder.iterencode(data)
