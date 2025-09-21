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
    # path('ajax/hsn_lookup/', views.hsn_lookup, name='hsn_lookup'),
    # path('ajax/products_by_hsn/', views.products_by_hsn, name='products_by_hsn'),
    path('ajax/gst_hsn_lookup/', views.gst_hsn_lookup, name='gst_hsn_lookup'),
    path('ajax/hsn_tax_lookup/', views.hsn_tax_lookup, name='hsn_tax_lookup'),
    # Tax Master
    path('ajax/create_tax_from_hsn/', views.ajax_create_tax_from_hsn, name='ajax_create_tax_from_hsn'),

path('taxes/', views.taxes_list, name='taxes_list'),
path('taxes/new/', views.taxes_add, name='taxes_add'),
path('taxes/<int:pk>/edit/', views.taxes_edit, name='taxes_edit'),
path('taxes/<int:pk>/delete/', views.taxes_delete, name='taxes_delete'),

# Chart of Accounts
# import views accordingly: from yourapp import views
path('accounts/', views.accounts_list, name='accounts_list'),
path('accounts/new/', views.accounts_add, name='accounts_add'),
path('accounts/<int:pk>/edit/', views.accounts_edit, name='accounts_edit'),
path('accounts/<int:pk>/delete/', views.accounts_delete, name='accounts_delete'),

# path('purchase_orders/', views.purchase_order_list, name='purchase_order_list'),
# path('purchase_orders/new/', views.purchase_order_add, name='purchase_order_add'),
# yourapp/urls.py
path('purchase_orders/', views.purchase_orders_list, name='purchase_orders_list'),
path('purchase_orders/new/', views.purchase_order_add, name='purchase_order_add'),
path('purchase_orders/<int:pk>/', views.purchase_order_detail, name='purchase_order_detail'),
path('purchase_orders/<int:pk>/convert/', views.purchase_order_convert_to_bill, name='purchase_order_convert_to_bill'),

path('ajax/active_taxes/', views.ajax_active_taxes, name='ajax_active_taxes'),
path('vendor_bills/<int:pk>/confirm/', views.vendor_bill_confirm, name='vendor_bill_confirm'),
path('products/info/<int:pk>/', views.product_info, name='product_info'),

# yourapp/urls.py
path('vendor_bills/', views.vendor_bills_list, name='vendor_bills_list'),
path('vendor_bills/new/', views.vendor_bill_add, name='vendor_bill_add'),
# path('vendor_bills/<int:pk>/', views.vendor_bill_detail, name='vendor_bill_detail'),
# path('vendor_bills/<int:pk>/confirm/', views.vendor_bill_confirm_view, name='vendor_bill_confirm'),
path('vendor_bills/<int:bill_pk>/payments/new/', views.payment_add, name='payment_add'),

# path('vendor_bills/<int:pk>/confirm/', views.vendor_bill_confirm, name='vendor_bill_confirm'),
# ensure vendor_bill_detail exists:
path('vendor_bills/<int:pk>/', views.vendor_bill_detail, name='vendor_bill_detail'),

path('reports/partner/<int:partner_id>/', views.partner_ledger, name='partner_ledger'),
path('reports/profit-loss/', views.profit_and_loss, name='profit_and_loss'),
path('reports/balance-sheet/', views.balance_sheet, name='balance_sheet'),
 path('vendor-bills/<int:pk>/pay/', views.vendor_bill_payment, name='vendor_bill_payment'),

 path('sales/orders/', views.sales_order_list, name='sales_order_list'),
 path('sales/orders/new/', views.sales_order_create, name='sales_order_create'),
 path('sales/orders/<int:pk>/', views.sales_order_detail, name='sales_order_detail'),
 path('sales/orders/<int:pk>/add-line/', views.sales_order_add_line, name='sales_order_add_line'),
 path('sales/orders/<int:pk>/confirm/', views.sales_order_confirm, name='sales_order_confirm'),


 path('sales/order/<int:so_pk>/create-invoice/', views.create_invoice_from_so, name='create_invoice_from_so'),
path('invoices/<int:pk>/confirm/', views.customer_invoice_confirm, name='customer_invoice_confirm'),
path('invoices/<int:pk>/pay/', views.customer_invoice_receive_payment, name='customer_invoice_receive_payment'),
# detail/list views not shown here but should exist (customer_invoice_detail)
path('invoices/', views.customer_invoices_list, name='customer_invoices_list'),
path('invoices/<int:pk>/', views.customer_invoice_detail, name='customer_invoice_detail'),

 path('portal/invoices/', views.customer_portal_invoices, name='customer_portal_invoices'),
    path('portal/invoice/<int:pk>/', views.customer_portal_invoice_detail, name='customer_portal_invoice_detail'),

    # Payment
    # path('portal/invoice/<int:pk>/pay/', views.portal_invoice_pay, name='portal_invoice_pay'),
    path('portal/payment/callback/<int:payment_id>/', views.portal_payment_callback, name='portal_payment_callback'),
     path('portal/impersonate/<int:contact_id>/', views.portal_impersonate, name='portal_impersonate'),

      path("portal/login/", views.customer_login, name="customer_login"),
    path("portal/logout/", views.customer_logout, name="customer_logout"),
    path("portal/invoices/", views.customer_portal_invoices, name="customer_portal_invoices"),
    # path("portal/invoices/<int:invoice_id>/pay/", views.customer_portal_pay, name="customer_portal_pay"),

path('portal/invoices/<int:invoice_id>/pay/create-order/', views.portal_invoice_pay_create_order, name='portal_invoice_pay_create_order'),
    # path('portal/invoices/<int:invoice_id>/pay/verify/', views.portal_invoice_razorpay_verify, name='portal_invoice_razorpay_verify'),
    path('razorpay/webhook/', views.razorpay_webhook, name='razorpay_webhook'),  # optional

    path("portal/invoices/<int:invoice_id>/pay/", views.portal_invoice_pay_create_order, name="portal_invoice_pay_create_order"),
path("portal/invoices/<int:invoice_id>/razorpay-verify/", views.portal_invoice_razorpay_verify, name="portal_invoice_razorpay_verify"),

]