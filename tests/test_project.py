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
