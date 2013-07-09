from django import template
from django.template import Library, Node, Variable
from attachments.forms import AttachmentForm
from attachments.views import add_url_for_obj
from django.core.urlresolvers import reverse
from django.contrib.contenttypes.models import ContentType
from attachments.models import Attachment
from attachments.forms import AttachmentForm
from django.utils.encoding import smart_text


register = Library()


class BaseAttachmentNode(Node):
    """
    Base helper class (abstract) for handling the get_comment_* template tags.
    Looks a bit strange, but the subclasses below should make this a bit more
    obvious.
    """

    @classmethod
    def handle_token(cls, parser, token):
        """
        Class method to parse get_comment_list/count/form and return a Node.
        """
        tokens = token.contents.split()
        if tokens[1] != 'for':
            raise template.TemplateSyntaxError(
                "Second argument in %r tag must be 'for'" % tokens[0])

        # {% get_whatever for obj as varname %}
        if len(tokens) == 5:
            if tokens[3] != 'as':
                raise template.TemplateSyntaxError(
                    "Third argument in %r must be 'as'" % tokens[0])
            obj, _, varname = tokens[2:]
            return cls(
                object_expr=parser.compile_filter(obj),
                as_varname=varname)

        # {% get_whatever for app.model pk as varname %}
        elif len(tokens) == 6:
            if tokens[4] != 'as':
                raise template.TemplateSyntaxError(
                    "Fourth argument in %r must be 'as'" % tokens[0])
            method_name, _, app_model, pk, _, varname = tokens
            return cls(
                ctype=BaseAttachmentNode.lookup_content_type(
                    app_model, method_name),
                object_pk_expr=parser.compile_filter(pk),
                as_varname=varname)

        else:
            raise template.TemplateSyntaxError(
                "%r tag requires 4 or 5 arguments" % tokens[0])

    @staticmethod
    def lookup_content_type(token, tagname):
        try:
            app, model = token.split('.')
        except ValueError:
            raise template.TemplateSyntaxError(
                "Third argument in %r must be in the "
                "format 'app.model'" % tagname)
        try:
            return ContentType.objects.get_by_natural_key(app, model)
        except ContentType.DoesNotExist:
            raise template.TemplateSyntaxError(
                "%r tag has non-existant content-type:"
                " '%s.%s'" % (tagname, app, model))

    def __init__(self, ctype=None, object_pk_expr=None, object_expr=None,
                 as_varname=None, attachment=None):
        if ctype is None and object_expr is None:
            raise template.TemplateSyntaxError(
                "Attachment nodes must be given either a literal object or a "
                "ctype and object pk.")
        self.attachment_model = Attachment
        self.as_varname = as_varname
        self.ctype = ctype
        self.object_pk_expr = object_pk_expr
        self.object_expr = object_expr
        self.attachment = attachment

    def render(self, context):
        qs = self.get_query_set(context)
        context[self.as_varname] = self.get_context_value_from_queryset(context, qs)
        return ''

    def get_query_set(self, context):
        ctype, object_pk = self.get_target_ctype_pk(context)
        if not object_pk:
            return self.attachment_model.objects.none()

        qs = self.attachment_model.objects.filter(
            content_type=ctype,
            object_id=smart_text(object_pk))

        return qs

    def get_target_ctype_pk(self, context):
        if self.object_expr:
            try:
                obj = self.object_expr.resolve(context)
            except template.VariableDoesNotExist:
                return None, None
            return ContentType.objects.get_for_model(obj), obj.pk
        else:
            return (
                self.ctype,
                self.object_pk_expr.resolve(context, ignore_failures=True))

    def get_context_value_from_queryset(self, context, qs):
        """Subclasses should override this."""
        raise NotImplementedError


class AttachmentFormNode(BaseAttachmentNode):
    """Insert a form for the comment model into the context."""

    def get_form(self, context):
        obj = self.get_object(context)
        if obj:
            f = AttachmentForm()
            f.form_url = add_url_for_obj(obj)
            return f
        else:
            return None

    def get_object(self, context):
        if self.object_expr:
            try:
                return self.object_expr.resolve(context)
            except template.VariableDoesNotExist:
                return None
        else:
            object_pk = self.object_pk_expr.resolve(
                context, ignore_failures=True)
            return self.ctype.get_object_for_this_type(pk=object_pk)

    def render(self, context):
        context[self.as_varname] = self.get_form(context)
        return ''

@register.inclusion_tag('attachments/add_form.html', takes_context=True)
def attachment_form(context, obj):
    """
    Renders a "upload attachment" form.
    
    The user must own ``attachments.add_attachment permission`` to add
    attachments.
    """
    if context['user'].has_perm('attachments.add_attachment'):
        return {
            'form': AttachmentForm(),
            'form_url': add_url_for_obj(obj),
            'next': context['request'].build_absolute_uri(),
        }
    else:
        return {
            'form': None,
        }


@register.tag
def get_attachment_form(parser, token):
    """
    Get a (new) form object to upload a new attachment

    Syntax::

        {% get_attachment_form for [object] as [varname] %}
        {% get_attachment_for for [app].[model] [object_id] as [varname] %}
    """
    return AttachmentFormNode.handle_token(parser, token)


@register.inclusion_tag('attachments/delete_link.html', takes_context=True)
def attachment_delete_link(context, attachment):
    """
    Renders a html link to the delete view of the given attachment. Returns
    no content if the request-user has no permission to delete attachments.
    
    The user must own either the ``attachments.delete_attachment`` permission
    and is the creator of the attachment, that he can delete it or he has
    ``attachments.delete_foreign_attachments`` which allows him to delete all
    attachments.
    """
    if context['user'].has_perm('delete_foreign_attachments') \
       or (context['user'] == attachment.creator and \
           context['user'].has_perm('attachments.delete_attachment')):
        return {
            'next': context['request'].build_absolute_uri(),
            'delete_url': reverse('delete_attachment', kwargs={'attachment_pk': attachment.pk})
        }
    return {'delete_url': None,}



class AttachmentsForObjectNode(Node):
    def __init__(self, obj, var_name):
        self.obj = obj
        self.var_name = var_name

    def resolve(self, var, context):
        """Resolves a variable out of context if it's not in quotes"""
        if var[0] in ('"', "'") and var[-1] == var[0]:
            return var[1:-1]
        else:
            return Variable(var).resolve(context)

    def render(self, context):
        obj = self.resolve(self.obj, context)
        var_name = self.resolve(self.var_name, context)
        context[var_name] = Attachment.objects.attachments_for_object(obj)
        return ''

@register.tag
def get_attachments_for(parser, token):
    """
    Resolves attachments that are attached to a given object. You can specify
    the variable name in the context the attachments are stored using the `as`
    argument. Default context variable name is `attachments`.

    Syntax::

        {% get_attachments_for obj %}
        {% for att in attachments %}
            {{ att }}
        {% endfor %}

        {% get_attachments_for obj as "my_attachments" %}

    """
    def next_bit_for(bits, key, if_none=None):
        try:
            return bits[bits.index(key)+1]
        except ValueError:
            return if_none

    bits = token.contents.split()
    args = {
        'obj': next_bit_for(bits, 'get_attachments_for'),
        'var_name': next_bit_for(bits, 'as', '"attachments"'),
    }
    return AttachmentsForObjectNode(**args)