import time

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from core.middleware import SessionTimeoutMiddleware
from core.views_tasks import (
    combine_bug_description,
    create_bug_view,
    create_story_view,
    split_bug_description,
)


class BugDescriptionSectionsTests(TestCase):
    def test_split_combined_bug_description_for_editing(self):
        combined = (
            "A concise description.\n\n"
            "**Steps to Reproduce:**\n1. Open the page\n2. Click Save\n\n"
            "**Expected Behavior:**\nA validation message appears.\n\n"
            "**Actual Behavior:**\nA system error appears."
        )

        sections = split_bug_description(combined)

        self.assertEqual(sections["description"], "A concise description.")
        self.assertEqual(sections["steps_to_reproduce"], "1. Open the page\n2. Click Save")
        self.assertEqual(sections["expected_behavior"], "A validation message appears.")
        self.assertEqual(sections["actual_behavior"], "A system error appears.")

    def test_combining_edited_sections_preserves_storage_format(self):
        combined = combine_bug_description(
            "<p>A concise description.</p>",
            "<ol><li>Open the page</li></ol>",
            "<p>A validation message appears.</p>",
            "<p>A system error appears.</p>",
        )

        self.assertEqual(
            split_bug_description(combined),
            {
                "description": "<p>A concise description.</p>",
                "steps_to_reproduce": "<ol><li>Open the page</li></ol>",
                "expected_behavior": "<p>A validation message appears.</p>",
                "actual_behavior": "<p>A system error appears.</p>",
            },
        )


@override_settings(SESSION_COOKIE_AGE=1800)
class SessionTimeoutMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SessionTimeoutMiddleware(lambda request: HttpResponse('ok'))

    def _build_request(self, path='/', headers=None):
        request = self.factory.get(path, **(headers or {}))
        session_middleware = SessionMiddleware(lambda req: HttpResponse('ok'))
        session_middleware.process_request(request)
        request.session.save()
        return request

    def test_expired_page_session_redirects_to_login_and_preserves_ident_context(self):
        request = self._build_request('/dashboard/')
        request.session['user'] = {'email': 'user@example.com'}
        request.session['member_id'] = 12
        request.session['tenant_config'] = {'tenant_id': 5, 'domain_postfix': '@example.com'}
        request.session['ident_email'] = 'user@example.com'
        request.session['last_activity'] = time.time() - 1900
        request.session.save()

        response = self.middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login_password/')
        self.assertEqual(
            request.session.get('session_expired_message'),
            'Your session has expired. Please log in again.',
        )
        self.assertEqual(request.session.get('ident_email'), 'user@example.com')
        self.assertEqual(request.session.get('tenant_config'), {'tenant_id': 5, 'domain_postfix': '@example.com'})
        self.assertIsNone(request.session.get('user'))
        self.assertIsNone(request.session.get('member_id'))

    def test_expired_api_session_returns_401(self):
        request = self._build_request(
            '/api/people/list',
            headers={'HTTP_ACCEPT': 'application/json'},
        )
        request.session['user'] = {'email': 'user@example.com'}
        request.session['member_id'] = 12
        request.session['last_activity'] = time.time() - 1900
        request.session.save()

        response = self.middleware(request)

        self.assertEqual(response.status_code, 401)
        self.assertJSONEqual(response.content, {'error': 'Session expired'})

    def test_expired_media_request_redirects_to_login(self):
        request = self._build_request('/media/task_attachments/example.png')
        request.session['user'] = {'email': 'user@example.com'}
        request.session['member_id'] = 12
        request.session['last_activity'] = time.time() - 1900
        request.session.save()

        response = self.middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login_password/')

    def test_active_session_updates_last_activity_and_allows_request(self):
        request = self._build_request('/dashboard/')
        request.session['user'] = {'email': 'user@example.com'}
        request.session['member_id'] = 12
        request.session['last_activity'] = time.time() - 60
        previous = request.session['last_activity']
        request.session.save()

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(request.session['last_activity'], previous)


class TaskCreateAuthRedirectTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _build_request(self, path):
        request = self.factory.get(path)
        session_middleware = SessionMiddleware(lambda req: HttpResponse('ok'))
        session_middleware.process_request(request)
        request.session.save()
        return request

    def test_create_story_redirects_to_password_login_when_tenant_context_exists(self):
        request = self._build_request('/tasks/create/story/')
        request.session['tenant_config'] = {'tenant_id': 5, 'domain_postfix': '@example.com'}
        request.session['ident_email'] = 'user@example.com'
        request.session.save()

        response = create_story_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login_password/')
        self.assertEqual(
            request.session.get('session_expired_message'),
            'Your session has expired. Please log in again.',
        )

    def test_create_bug_redirects_to_identify_without_tenant_context(self):
        request = self._build_request('/tasks/create/bug/')

        response = create_bug_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
