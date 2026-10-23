from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import TemplateView
from rest_framework.routers import DefaultRouter

from studio import views

router = DefaultRouter()
router.register('bookings', views.BookingViewSet, basename='bookings')
router.register('portfolio', views.PortfolioViewSet, basename='portfolio')
router.register('reviews', views.ReviewViewSet, basename='reviews')
router.register('faq', views.FAQViewSet, basename='faq')

urlpatterns = [
    path('', TemplateView.as_view(template_name='index.html'), name='frontend'),
    path('health/', views.health),
    path('api/auth/csrf/', views.csrf),
    path('api/auth/request-code/', views.RequestCode.as_view()),
    path('api/auth/verify-code/', views.VerifyCode.as_view()),
    path('api/auth/logout/', views.Logout.as_view()),
    path('api/me/', views.Me.as_view()),
    path('api/me/profile/', views.MyProfile.as_view()),
    path('api/catalog/', views.Catalog.as_view()),
    path('api/team/', views.Team.as_view()),
    path('api/management/prices/', views.Prices.as_view()),
    path('api/management/availability/', views.Availability.as_view()),
    path('api/management/bindings/', views.Bindings.as_view()),
    path('api/management/bindings/<int:pk>/', views.BindingDelete.as_view()),
    path('api/management/change-requests/<int:pk>/decision/', views.ChangeDecision.as_view()),
    path('api/', include(router.urls)),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
