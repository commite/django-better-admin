from django.template import Library

from django.utils.text import slugify
from django.template.loader import get_template
from django.utils.safestring import mark_safe
from django.db import models

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.urlresolvers import reverse


register = Library()


@register.simple_tag
def render_show_action(show_action, request, original):
    return mark_safe(show_action.render(request, original))


@register.inclusion_tag('betteradmin/includes/show_field.html', takes_context=True)
def readonly_field(context, field):
    opts = context.get('opts', None)
    form = field.form
    base_field = form.fields[field.field['name']]
    original = context.get('original', None)

    return {
        'opts': opts,
        'form': form,
        'original': original,
        'field': field,
        'base_field': base_field,
    }


@register.filter
def is_email(field):
    opts = field.model_admin.opts
    db_field = opts.get_field(field.field['name'])
    return isinstance(db_field, (models.EmailField,))


@register.filter
def is_url(field):
    opts = field.model_admin.opts
    db_field = opts.get_field(field.field['name'])
    return isinstance(db_field, (models.URLField,))


@register.filter
def is_foreign_key(field):
    opts = field.model_admin.opts
    db_field = opts.get_field(field.field['name'])
    if isinstance(db_field, (models.ForeignKey,)):
        admin_site = field.model_admin.admin_site
        return admin_site.is_registered(db_field.related_model)
    return False


@register.simple_tag
def admin_show_url(original, field):
    admin_site = field.model_admin.admin_site.name
    fk_instance = getattr(original, field.field['name'])

    content_type = ContentType \
        .objects \
        .get_for_model(fk_instance.__class__)
    return reverse("%s:%s_%s_show" % (
        admin_site,
        content_type.app_label,
        content_type.model),
        args=(fk_instance.id,))
