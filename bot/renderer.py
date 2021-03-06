# -*- coding: utf-8 -*-
from __future__ import absolute_import
import re
from . cleaner import clean_html
from . api import XPathWrapper
from functools import partial

def render(dyn_id, post):
    """ Принимает объект api.Post.
        Возвращает текстовую версию поста и его HTML версию.
    """
    func = globals().get('_render_' + post.post_type, _render_generic)
    return func(dyn_id, post)


_ya_user_re1 = re.compile(r'<ya user="(.+?)" title="(.+?)" uid="(.+?)"/>')
_ya_user_re2 = re.compile(r'<ya user="(.+?)" uid="(.+?)"/>')
_ya_smile_re = re.compile(r'<ya-smile text="(.+?)" code=".+?" theme=".+?"/>')
_img1_re = re.compile(r'<img.*?src="(.+?)".+?alt="".*?/>', re.DOTALL)
_img2_re = re.compile(r'<img.*?src="(.+?)".+?alt="(.+?)".*?/>', re.DOTALL)
_img3_re = re.compile(r'<img.*?src="(.+?)".*?/>', re.DOTALL)

def _get_params(dyn_id, post):
    return dict(
        dyn_id = dyn_id,
        author = post.author,
        sex = post.xpath('a:author/y:sex')[0].text,
        author_id = post.xpath('a:author/y:id')[0].text,
        post_link = post.get_link('alternate'),
    )

def _sex(male_text, femail_text, sex):
    """ Выбирает тот или иной текст в зависимости от пола. """
    if sex == 'woman':
        return femail_text
    return male_text


def _strip_tags(html):
    if not isinstance(html, basestring):
        return html

    html = re.sub(r' *<br[ /]*?> *', '\n', html)
    return re.sub(r'<.*?>', '', html)


def _prepare_text(text):
    if not isinstance(text, basestring):
        return text

    def fix_url(url):
        """ Чинит урл, убирая из него переводы строк и лишние пробелы. """
        return ''.join(
            part.strip()
            for part in url.split('\n')
        )

    text = _ya_user_re1.sub(r'<a href="http://\1.ya.ru">\2</a>', text)
    text = _ya_user_re2.sub(r'<a href="http://\1.ya.ru">\1</a>', text)
    text = _ya_smile_re.sub(r'\1', text)
    text = _img1_re.sub(
        lambda m: ur'Картинка: %s' % fix_url(m.group(1)),
        text
    )
    text = _img2_re.sub(
        lambda m: ur'Картинка %s: %s' % (m.group(2), fix_url(m.group(1))),
        text
    )
    text = _img3_re.sub(
        lambda m: ur'Картинка: %s' % fix_url(m.group(1)),
        text
    )
    text = clean_html(text)
    return text


def _render_link(dyn_id, post):
    params = _get_params(dyn_id, post)
    params['action'] = _sex(u'дал', u'дала', params['sex'])
    message = u'#%(dyn_id)0.2d %(author)s %(action)s ссылку: ' % params
    html_message = message

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


def _render_status(dyn_id, post):
    params = _get_params(dyn_id, post)
    content_type, content = post.content
    params['content'] = _strip_tags(_prepare_text(content))
    params['action'] = _sex(u'сменил', u'сменила', params['sex'])

    if params['content']:
        message = u'#%(dyn_id)0.2d %(author)s %(action)s настроение: %(content)s ' % params
    else:
        message = u'#%(dyn_id)0.2d %(author)s теперь не в настроении' % params
    return message, message


def _render_congratulation(dyn_id, post):
    params = _get_params(dyn_id, post)
    message = [u'#%(dyn_id)0.2d %(author)s поздравляет: ' % params]
    html_message = [message[0]]

    content_type, content = post.content
    if content:
        content = _prepare_text(content)
        message.append(_strip_tags(content))
        html_message.append(content)

    message = u'\n'.join(message)
    html_message = u'<br/>'.join(html_message)
    return message, html_message


def _rndr_friend_unfriend(dyn_id, post, message_template = ''):
    params = _get_params(dyn_id, post)
    params['person_name'] = post.xpath('y:meta/y:person/y:name')[0].text
    message = [message_template % params]
    html_message = [message[0]]

    content_type, content = post.content
    if content:
        content = _prepare_text(content)
        message.append(_strip_tags(content))
        html_message.append(content)

    message = u'\n'.join(message)
    html_message = u'<br/>'.join(html_message)
    return message, html_message


_render_friend = partial(
    _rndr_friend_unfriend,
    message_template = u'#%(dyn_id)0.2d %(author)s подружился с %(person_name)s'
)


_render_unfriend = partial(
    _rndr_friend_unfriend,
    message_template = u'#%(dyn_id)0.2d %(author)s поссорился с %(person_name)s'
)


def _render_photo(dyn_id, post):
    params = _get_params(dyn_id, post)
    params['action'] = _sex(u'вывесил', u'вывесила', params['sex'])

    images = map(XPathWrapper, post.xpath('y:meta/y:image'))
    if len(images) > 1:
        message = u'#%(dyn_id)0.2d %(author)s %(action)s фотки: ' % params
    else:
        message = u'#%(dyn_id)0.2d %(author)s %(action)s фотку: ' % params

    html_message = message

    for image in images:
        image_author_id = image.xpath('y:person/y:id')[0].text
        image_url = image.xpath('y:url')[0].text

        message += '\n' + image_url
        html_message += '<br /><a href="%s">%s</a>' % (image_url, image_url)

        if image_author_id != params['author_id']:
            image_author = image.xpath('y:person/y:name')[0].text
            image_author_url = image.xpath('y:person/y:link[@rel="self"]')[0].text
            message += ', ' + image_author
            html_message += ', <a href="%s">%s</a>' % (image_author_url, image_author)

    content_type, content = post.content
    content = _prepare_text(content)

    if content:
        message += '\n' + _strip_tags(content)
        html_message += '<br />' + content

    message += u'\nИсточник: %(post_link)s' % params
    return message, html_message


def _render_generic(dyn_id, post):
    type_ = u', ' + post.post_type
    if type_ == u', text':
        type_ = u' написал'

    params = _get_params(dyn_id, post)
    params['type'] = type_
    parts = [
        u'#%(dyn_id)0.2d %(author)s%(type)s: ' % params
    ]
    html_parts = [
        parts[0]
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
    html_parts.append(u'<a href="%(post_link)s">Источник</a>.' % params)
    message = u'\n'.join(parts)
    html_message = u'<br/>'.join(html_parts)

    html_message = html_message.replace(u'&lt;', u'<')
    html_message = html_message.replace(u'&gt;', u'>')

    return message, html_message

