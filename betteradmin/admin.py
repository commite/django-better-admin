# -*- coding: utf-8 -*-
from django import forms
from django.contrib import admin
from django.contrib.admin.templatetags.admin_static import static
from django.contrib.admin import helpers
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.options import IS_POPUP_VAR, get_content_type_for_model, InlineModelAdmin
from django.contrib.admin.utils import quote, unquote, flatten_fieldsets
from django.contrib.auth import get_permission_codename
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User
from django.db import models
from django.http import Http404, HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from django.utils.encoding import force_unicode, force_text
from django.utils.html import escape
from django.template.response import TemplateResponse
from django.core.exceptions import FieldError
from django.views.generic import RedirectView
from django.forms.models import modelform_factory
from django.conf import settings

from functools import partial, update_wrapper
from collections import OrderedDict

SHOW = 4


class ShowModelAdminMixin(object):

    """
        Visualization view for any admin.
    """

    use_show_view = True
    use_show_view_log = False

    show_object_template = None
    change_form_template = 'betteradmin/change_form.html'

    """
        Override generic ChangeList to link to show views instead of change
    """
    def get_changelist(self, request, **kwargs):
        return ShowModelAdminMixin.ShowChangeList

    class ShowChangeList(ChangeList):

        """ChangeList with support for model 'view' page"""

        def url_for_result(self, result):
            pk = getattr(result, self.pk_attname)
            return reverse('admin:%s_%s_show' % (self.opts.app_label,
                                                   self.opts.model_name),
                           args=(quote(pk),),
                           current_app=self.model_admin.admin_site.name)

    def get_urls(self):
        from django.conf.urls import url
        urlpatterns = super(ShowModelAdminMixin, self).get_urls()

        # Replace the redirect pattern to go to show instead of change
        for pattern in urlpatterns:
            if pattern.regex.pattern == '^(.+)/$':
                urlpatterns.remove(pattern)

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)
            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        info = self.model._meta.app_label, self.model._meta.model_name
        urlpatterns = [
            url(r'^(.+)/show/$', wrap(self.admin_site.admin_view(self.show_view)), name='%s_%s_show' % info),
        ] + urlpatterns + [
            url(r'^(.+)/$', wrap(RedirectView.as_view(
                pattern_name='%s:%s_%s_show' % ((self.admin_site.name,) + info)
            ))),
        ]

        return urlpatterns

    def is_show_view(self, request):
        info = self.model._meta.app_label, self.model._meta.model_name
        url_name = request.resolver_match.url_name
        return url_name == '%s_%s_show' % info

    def get_inline_instances(self, request, obj=None):
        inline_instances = []
        for inline_class in self.inlines:
            # TODO Find a better way to check if we are on show view
            if self.is_show_view(request):
                inline_class = type(
                    'Show' + inline_class.__name__,
                    (ShowInlineModelAdmin, inline_class),
                    {})
                inline = inline_class(self.model, self.admin_site)
                if inline.has_show_permission(request, obj):
                    inline_instances.append(inline)
            else:
                inline = inline_class(self.model, self.admin_site)
                if request:
                    if not (inline.has_add_permission(request) or
                            inline.has_change_permission(request, obj) or
                            inline.has_delete_permission(request, obj)):
                        continue
                    if not inline.has_add_permission(request):
                        inline.max_num = 0
                inline_instances.append(inline)

        return inline_instances

    def has_show_permission(self, request, obj=None):
        opts = self.opts
        codename = get_permission_codename('show', opts)
        change_permission = self.has_change_permission(request, obj)
        return change_permission or request.user.has_perm("%s.%s" % (opts.app_label, codename))

    def get_show_object_template(self):
        opts = self.model._meta
        app_label = opts.app_label
        app_name = self.admin_site.name
        return self.show_object_template or [
            "%s/%s/%s/show_object.html" % (app_name, app_label,
                                           opts.object_name.lower()),
            "%s/%s/show_object.html" % (app_name, app_label),
            "%s/show_object.html" % app_name] + [
                "betteradmin/%s/%s/show_object.html" % (
                    app_label, opts.object_name.lower()),
                "betteradmin/%s/show_object.html" % (app_label),
                "betteradmin/show_object.html",
            ]

    def show_view(self, request, object_id, form_url='', extra_context=None):
        model = self.model
        opts = model._meta
        obj = self.get_object(request, unquote(object_id))

        if not self.has_show_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % {
                'name': force_text(opts.verbose_name), 'key': escape(object_id)})

        ModelForm = self.get_show_form(request, obj)
        form = ModelForm(instance=obj)

        adminForm = helpers.AdminForm(
            form,
            list(self.get_fieldsets(request, obj)),
            self.get_prepopulated_fields(request, obj),
            readonly_fields=form.fields.keys(),  # All fields readonly
            model_admin=self)
        media = self.media + adminForm.media
        opts = self.model._meta

        formsets, inline_instances = self._create_formsets(request, obj, change=True)
        inline_formsets = self.get_show_inline_formsets(request, formsets, inline_instances, obj)
        for inline_formset in inline_formsets:
            media = media + inline_formset.media

        context = dict(
            self.admin_site.each_context(request),
            title=_(u'View {verbose_name}').format(
                verbose_name=force_unicode(opts.verbose_name)),
            adminform=adminForm,
            view_name='show',
            object_id=object_id,
            original=obj,
            is_popup=(IS_POPUP_VAR in request.POST or
                      IS_POPUP_VAR in request.GET),
            media=media,
            inline_admin_formsets=inline_formsets,
            errors=helpers.AdminErrorList(form, []),
            app_label=opts.app_label,
            is_show_view=True,
            has_add_permission=self.has_add_permission(request),
            has_change_permission=self.has_change_permission(request, obj),
            has_delete_permission=self.has_delete_permission(request, obj),
            has_absolute_url=hasattr(self.model, 'get_absolute_url'),
            opts=opts,
        )
        context.update(extra_context or {})

        self.log_show(request, obj)
        return TemplateResponse(request, self.get_show_object_template(), context)

    def get_show_inline_formsets(self, request, formsets, inline_instances, obj=None):
        inline_admin_formsets = []
        for inline, formset in zip(inline_instances, formsets):
            fieldsets = list(inline.get_fieldsets(request, obj))
            # All fields will be readonly
            readonly = list(inline.get_fields(request))
            prepopulated = dict(inline.get_prepopulated_fields(request, obj))
            inline_admin_formset = helpers.InlineAdminFormSet(inline, formset,
                fieldsets, prepopulated, readonly, model_admin=self)
            inline_admin_formsets.append(inline_admin_formset)
        return inline_admin_formsets

    def get_show_form(self, request, obj=None, **kwargs):
        """
        Returns a Form class for use in the admin show view.
        This is used by show_view, and doesn't take into account
        the readonly_fields, as all will be shown as readonly by the admin
        form.
        """
        if 'fields' in kwargs:
            fields = kwargs.pop('fields')
        else:
            fields = flatten_fieldsets(self.get_fieldsets(request, obj))
        if self.exclude is None:
            exclude = []
        else:
            exclude = list(self.exclude)

        if self.exclude is None and hasattr(self.form, '_meta') and self.form._meta.exclude:
            # Take the custom ModelForm's Meta.exclude into account only if the
            # ModelAdmin doesn't define its own.
            exclude.extend(self.form._meta.exclude)
        # if exclude is an empty list we pass None to be consistent with the
        # default on modelform_factory
        exclude = exclude or None

        # Remove declared form fields which are in readonly_fields.
        readonly_fields = self.get_readonly_fields(request, obj)
        new_attrs = OrderedDict(
            (f, None) for f in readonly_fields
            if f in self.form.declared_fields
        )
        form = type(self.form.__name__, (self.form,), new_attrs)

        defaults = {
            "form": form,
            "fields": fields,
            "exclude": exclude,
            "formfield_callback": partial(self.formfield_for_dbfield, request=request),
        }
        defaults.update(kwargs)

        if defaults['fields'] is None and not modelform_defines_fields(defaults['form']):
            defaults['fields'] = forms.ALL_FIELDS

        try:
            return modelform_factory(self.model, **defaults)
        except FieldError as e:
            raise FieldError('%s. Check fields/fieldsets/exclude attributes of class %s.'
                             % (e, self.__class__.__name__))

    def log_show(self, request, object):
        """
        Log that an object has been successfully showed.

        The default implementation check for use_show_view_log
        If false (default) does not anything
        If true creates an admin LogEntry object.
        """
        if self.use_show_view_log:
            self._create_log_entry(request, object, SHOW)

    def _create_log_entry(self, request, object, action_flag):
        from django.contrib.admin.models import LogEntry
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(object).pk,
            object_id=object.pk,
            object_repr=force_text(object),
            action_flag=action_flag,
        )


class ShowInlineModelAdmin(object):
    extra = 0
    max_num = 0

    def get_queryset(self, request):
        return super(InlineModelAdmin, self).get_queryset(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_show_permission(self, request, obj=None):
        opts = self.opts
        codename = get_permission_codename('show', opts)
        change_permission = self.has_change_permission(request, obj)
        return change_permission or request.user.has_perm("%s.%s" % (opts.app_label, codename))


# Register your models here.
class BetterModelAdmin(ShowModelAdminMixin, admin.ModelAdmin):

    def response_post_save_add(self, request, obj):
        """
            Overwritten to go to show view instead of changelist_view after
            save button has been pressed when adding a new object.
        """
        opts = self.model._meta
        if self.has_change_permission(request, None):
            post_url = reverse('admin:%s_%s_show' %
                               (opts.app_label, opts.model_name),
                               args=[obj.pk],
                               current_app=self.admin_site.name)
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, post_url)
        else:
            post_url = reverse('admin:index',
                               current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)

    def response_post_save_change(self, request, obj):
        """
            Overwritten to go to show view instead of changelist_view  after
            save button has been pressed when editing a new object.
        """
        opts = self.model._meta

        if self.has_change_permission(request, None):
            post_url = reverse('admin:%s_%s_show' %
                               (opts.app_label, opts.model_name),
                               args=[obj.pk],
                               current_app=self.admin_site.name)
            preserved_filters = self.get_preserved_filters(request)
            post_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, post_url)
        else:
            post_url = reverse('admin:index',
                               current_app=self.admin_site.name)
        return HttpResponseRedirect(post_url)


class BetterAdminSite(admin.AdminSite):
    """
    An BetterAdminSite object encapsulates an instance of the Django admin application, ready
    to be hooked in to your URLconf. Models are registered with the AdminSite using the
    register() method, and the get_urls() method can then be used to access Django view
    functions that present a full admin interface for the collection of registered
    models.
    """

    def register(self, model_or_iterable, admin_class=None, **options):
        """
            Override to indicate BetterModelAdmin as base ModelAdmin class
        """
        if not admin_class:
            admin_class = BetterModelAdmin
        super(BetterAdminSite, self).register(model_or_iterable, admin_class=admin_class, **options)


site = BetterAdminSite()
