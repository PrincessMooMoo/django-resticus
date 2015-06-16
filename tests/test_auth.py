import base64
from django.test import TestCase
from restless.compat import json, get_user_model
from .client import TestClient
from .testapp.models import Publisher, Author, Book


class TestAuth(TestCase):
    def setUp(self):
        self.client = TestClient()
        self.user = get_user_model().objects.create_user(
            username='foo',
            password='bar'
        )

    def test_login_success(self):
        """Test that correct username/password login succeeds"""
        r = self.client.post('session_auth', data={
            'username': 'foo', 'password': 'bar',
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json['data']['username'], 'foo')

    def test_login_failure(self):
        """Test that incorrect username/password login fails"""
        r = self.client.post('session_auth', data={
            'username': 'nonexistent', 'password': 'pwd',
        })
        self.assertEqual(r.status_code, 403)

    def test_session_auth_success(self):
        """Test that the Session Auth succeeds"""
        self.client.login(username='foo', password='bar')
        r = self.client.get('session_auth')
        self.assertEqual(r.status_code, 200)

    def test_session_auth_failure(self):
        """Test that the Session Auth fails"""
        r = self.client.get('session_auth')
        self.assertEqual(r.status_code, 403)

    def test_basic_auth_challenge(self):
        """Test that HTTP Basic Auth challenge is issued"""
        r = self.client.get('basic_auth')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r['WWW-Authenticate'], 'Basic realm="api"')

    def test_basic_auth_success(self):
        """Test that HTTP Basic Auth succeeds"""
        r = self.client.get('basic_auth', extra={
            'HTTP_AUTHORIZATION': 'Basic {0}'.format(
                base64.b64encode(b'foo:bar').decode('ascii')),
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json['id'], self.user.id)

    def test_basic_auth_failure(self):
        """Test that HTTP Basic Auth fails"""
        r = self.client.get('basic_auth', extra={
            'HTTP_AUTHORIZATION': 'Basic {0}'.format(
                base64.b64encode(b'nonexistent:pwd').decode('ascii')),
        })
        self.assertEqual(r.status_code, 401)

    def test_basic_auth_invalid_auth_payload(self):
        """Test that invalid Basic Auth payload doesn't crash the pasrser"""
        r = self.client.get('basic_auth', extra={
            'HTTP_AUTHORIZATION': 'Basic xyz',
        })
        self.assertEqual(r.status_code, 401)
