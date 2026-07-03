from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Accounts


class AccountsCreationForm(UserCreationForm):
    class Meta:
        model  = Accounts
        fields = ('email', 'username', 'first_name', 'last_name', 'nickname')


class AccountsChangeForm(UserChangeForm):
    class Meta:
        model  = Accounts
        fields = ('email', 'username', 'first_name', 'last_name', 'nickname',
                  'phone_number', 'is_active', 'is_admin', 'is_staff',
                  'is_superadmin')


class AccountsAdmin(UserAdmin):
    form     = AccountsChangeForm
    add_form = AccountsCreationForm

    list_display       = ('email', 'first_name', 'last_name', 'nickname', 'username',
                          'registration_id', 'is_active', 'is_admin',
                          'date_joined', 'last_login')
    list_display_links = ('email', 'first_name', 'last_name')
    list_filter        = ('is_active', 'is_admin', 'is_staff')
    search_fields      = ('email', 'username', 'first_name', 'last_name', 'nickname',
                          'phone_number', 'registration_id')
    ordering           = ('-date_joined',)
    readonly_fields    = ('date_joined', 'last_login', 'registration_id')
    filter_horizontal  = ()

    fieldsets = (
        ('Login Info',    {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'nickname', 'username', 'phone_number', 'registration_id')}),
        ('Permissions',   {'fields': ('is_active', 'is_admin', 'is_staff', 'is_superadmin')}),
        ('Timestamps',    {'fields': ('date_joined', 'last_login')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'username', 'first_name', 'last_name',
                        'password1', 'password2', 'is_active', 'is_admin'),
        }),
    )


admin.site.register(Accounts, AccountsAdmin)