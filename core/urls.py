from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("help/", views.help_page, name="help"),
    path("materials/", views.material_list, name="material_list"),
    path("locations/", views.location_list, name="location_list"),

    # Authentication
    path("register/", views.register_view, name="register"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Designs & Simulation
    path("dashboard/", views.dashboard, name="dashboard"),
    path("designs/new/", views.design_create, name="design_create"),
    path("designs/<int:pk>/", views.design_detail, name="design_detail"),
    path("designs/<int:pk>/edit/", views.design_edit, name="design_edit"),
    path("designs/<int:pk>/duplicate/", views.design_duplicate, name="design_duplicate"),
    path("designs/<int:pk>/delete/", views.design_delete, name="design_delete"),
    path("designs/<int:pk>/export/csv/", views.export_csv, name="export_csv"),
    path("designs/<int:pk>/export/pdf/", views.export_pdf, name="export_pdf"),
    path("compare/", views.compare_designs, name="compare_designs"),
]
