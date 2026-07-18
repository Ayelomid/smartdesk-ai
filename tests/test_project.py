"""Regression tests that do not modify project data."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import app
from model.predict import predict


class SmartDeskTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_login_pages_and_error_page(self):
        self.assertEqual(self.client.get('/login').status_code, 200)
        self.assertEqual(self.client.get('/admin/login').status_code, 200)
        self.assertEqual(self.client.get('/does-not-exist').status_code, 404)

    def login_as(self, username, password, admin=False):
        path = '/admin/login' if admin else '/login'
        self.client.get(path)
        with self.client.session_transaction() as session:
            token = session['_csrf_token']
        return self.client.post(
            path,
            data={'username': username, 'password': password, '_csrf_token': token},
            follow_redirects=False
        )

    def test_user_and_admin_profile_pages(self):
        user_login = self.login_as('user', 'user123')
        self.assertEqual(user_login.status_code, 302)
        user_profile = self.client.get('/profile')
        self.assertEqual(user_profile.status_code, 200)
        self.assertIn(b'Personal details', user_profile.data)
        self.assertIn(b'Change password', user_profile.data)

        self.client = app.test_client()
        admin_login = self.login_as('admin', 'admin123', admin=True)
        self.assertEqual(admin_login.status_code, 302)
        admin_profile = self.client.get('/profile')
        self.assertEqual(admin_profile.status_code, 200)
        self.assertIn(b'Administrator', admin_profile.data)

    def test_common_complaints(self):
        cases = {
            'I forgot my password': 'password_reset',
            'printer says offline': 'printer_problem',
            'my microphone is not working': 'audio_issue',
            'I clicked a phishing link': 'phishing',
            'my disk is full': 'storage_full',
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(predict(query)['intent'], expected)

    def test_unknown_request_escalates(self):
        result = predict('purple elephant sandwich orbit')
        self.assertEqual(result['intent'], 'unknown')
        self.assertTrue(result['escalate'])


if __name__ == '__main__':
    unittest.main()
