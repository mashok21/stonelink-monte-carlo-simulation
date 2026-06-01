from django.urls import path
from .views import SimulatePortfolioView

urlpatterns = [
    path('simulate/', SimulatePortfolioView.as_view(), name='simulate'),
]
