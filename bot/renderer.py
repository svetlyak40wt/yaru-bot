# -*- coding: utf-8 -*-
import re
from pdb import set_trace

def render(hash, post):
    """ Принимает объект api.Post.
        Возвращает текстовую версию поста и его HTML версию.
    """
    func = globals().get('_render_' + post.post_type, _render_generic)
    return func(hash, post)


_ya_user_re1 = re.compile(r'<ya user="(.+?)" title="(.+?)" uid="(.+?)"/>')
_ya_user_re2 = re.compile(r'<ya user="(.+?)" uid="(.+?)"/>')
_ya_smile_re = re.compile(r'<ya-smile text="(.+?)" code=".+?" theme=".+?"/>')
_img1_re = re.compile(r'<img.*?src="(.+?)".+?alt="".*?/>')
_img2_re = re.compile(r'<img.*?src="(.+?)".+?alt="(.+?)".*?/>')
_img3_re = re.compile(r'<img.*?src="(.+?)".*?/>')

def _get_params(hash, post):
    return dict(
        hash = hash,
        author = post.author,
        post_link = post.get_link('alternate'),
    )


def _strip_tags(html):
    if not isinstance(html, basestring):
        return html

    html = re.sub(r' *<br[ /]*?> *', '\n', html)
    return re.sub(r'<.*?>', '', html)


def _prepare_text(text):
    if not isinstance(text, basestring):
        return text

    text = _ya_user_re1.sub(r'<a href="http://\1.ya.ru">\2</a>', text)
    text = _ya_user_re2.sub(r'<a href="http://\1.ya.ru">\1</a>', text)
    text = _ya_smile_re.sub(r'\1', text)
    text = _img1_re.sub(ur'Картинка: \1', text)
    text = _img2_re.sub(ur'Картинка \2: \1', text)
    text = _img3_re.sub(ur'Картинка: \1', text)
    return text


def _render_link(hash, post):
    params = _get_params(hash, post)
    message = u'#%(hash)s) %(author)s дал ссылку: ' % params
    html_message = u'#%(hash)s<a href="%(post_link)s">)</a> %(author)s дал ссылку: ' % params

    if post.title:
        message += '%s - %s' % (post.title, post.link_url)
        html_message += '<a href="%s">%s</a>' % (post.link_url, post.title)
    else:
        message += post.link_url
        html_message += '<a href="%s">%s</a>' % (post.link_url, post.link_url)

    content_type, content = post.content
    content = _prepare_text(content)

    if content:
        message += '\n' + _strip_tags(content)
        html_message += '<br />' + content

    message += u'\nИсточник: %(post_link)s' % params
    return message, html_message


def _render_status(hash, post):
    params = _get_params(hash, post)
    content_type, content = post.content
    params['content'] = _strip_tags(_prepare_text(content))

    if params['content']:
        message = u'#%(hash)s) %(author)s сменил настроение: %(content)s ' % params
        html_message = u'#%(hash)s<a href="%(post_link)s">)</a> %(author)s сменил настроение: %(content)s' % params
    else:
        message = u'#%(hash)s) %(author)s теперь не в настроении' % params
        html_message = u'#%(hash)s<a href="%(post_link)s">)</a> %(author)s теперь не в настроении' % params
    return message, html_message


def _render_congratulation(hash, post):
    params = _get_params(hash, post)
    message = [u'#%(hash)s) %(author)s поздравляет: ' % params]
    html_message = [u'#%(hash)s<a href="%(post_link)s">)</a> %(author)s поздравляет: ' % params]

    content_type, content = post.content
    if content:
        content = _prepare_text(content)
        message.append(_strip_tags(content))
        html_message.append(content)

    message = u'\n'.join(message)
    html_message = u'<br/>'.join(html_message)
    return message, html_message


def _render_generic(hash, post):
    type_ = u', ' + post.post_type
    if type_ == u', text':
        type_ = u' написал'

    params = _get_params(hash, post)
    params['type'] = type_
    parts = [
        u'#%(hash)s) %(author)s%(type)s: ' % params
    ]
    html_parts = [
        u'#%(hash)s<a href="%(post_link)s">)</a> %(author)s%(type)s: ' % params
    ]
    title = post.title

    content_type, content = post.content
    content = _prepare_text(content)

    if title:
        parts[0] += title
        html_parts[0] += title
        if content:
            parts.append(_strip_tags(content))
            html_parts.append(content)
    else:
        if content:
            parts[0] += _strip_tags(content)
            html_parts[0] += content

    parts.append(u'Источник: %(post_link)s' % params)
    message = u'\n'.join(parts)
    html_message = u'<br/>'.join(html_parts)

    html_message = html_message.replace(u'&lt;', u'<')
    html_message = html_message.replace(u'&gt;', u'>')

    return message, html_message

