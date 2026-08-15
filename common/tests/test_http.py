from django.test import RequestFactory, SimpleTestCase

from common.http import is_htmx_partial


class IsHtmxPartialTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_plain_request_is_not_partial(self):
        request = self.factory.get("/")

        self.assertFalse(is_htmx_partial(request))

    def test_htmx_fragment_request_is_partial(self):
        request = self.factory.get("/", HTTP_HX_REQUEST="true")

        self.assertTrue(is_htmx_partial(request))

    def test_boosted_navigation_is_not_partial(self):
        request = self.factory.get(
            "/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_BOOSTED="true",
        )

        self.assertFalse(is_htmx_partial(request))
