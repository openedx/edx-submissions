"""
Submission URLs.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from submissions.views.xqueue import XQueueViewSet

router = DefaultRouter()
router.register(r'', XQueueViewSet, basename='xqueue')

urlpatterns = [
    path('', include(router.urls)),
]
