from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('signup/', views.signup_view, name='signup'),
    path('create-user/', views.create_user_view, name='create_user'),   # admin-only
    path('contacts/', views.contacts_list, name='contacts_list'),
    path('contacts/new/', views.contacts_add, name='contacts_add'),
    path('contacts/<int:pk>/', views.contacts_detail, name='contacts_detail'),
    path('contacts/<int:pk>/edit/', views.contacts_edit, name='contacts_edit'),  # admin-only
    path('contacts/<int:pk>/delete/', views.contacts_delete, name='contacts_delete'),  # admin-only
    path('products/', views.products_list, name='products_list'),
    path('products/new/', views.products_add, name='products_add'),
    path('products/<int:pk>/', views.products_detail, name='products_detail'),
    path('products/<int:pk>/edit/', views.products_edit, name='products_edit'),  # admin-only
    path('products/<int:pk>/delete/', views.products_delete, name='products_delete'),  # admin-only
    path('ajax/hsn_lookup/', views.hsn_lookup, name='hsn_lookup'),
    path('ajax/products_by_hsn/', views.products_by_hsn, name='products_by_hsn'),



]