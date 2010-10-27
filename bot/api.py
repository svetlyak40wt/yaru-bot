#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

import datetime

from lxml import etree as ET
from twisted.web import client
from twisted.web.error import Error as WebError
from twisted.python import log
from twisted.internet.defer import inlineCallbacks, returnValue

from . utils import force_str

NAMESPACES = {
  'a': 'http://www.w3.org/2005/Atom',
  'y': 'http://api.yandex.ru/yaru/',
}

HOST = 'https://api-yaru.yandex.ru'


class InvalidAuthToken(RuntimeError):
    pass



class XPathWrapper(object):
    def __init__(self, xml):
        self._xml = xml

    def xpath(self, path):
        return self._xml.xpath(path, namespaces = NAMESPACES)



class Post(XPathWrapper):
    def __init__(self, xml, api):
        super(Post, self).__init__(xml)
        self._api = api


    def __getstate__(self):
        return (ET.tostring(self._xml), self._api)


    def __setstate__(self, state):
        self._xml = ET.fromstring(state[0])
        self._api = state[1]


    @property
    def post_type(self):
        return self.xpath('a:category[@scheme = "urn:ya.ru:posttypes"]')[0].attrib['term']


    @property
    def author(self):
        return self.xpath('a:author/a:name')[0].text


    @property
    def title(self):
        return self.xpath('a:title')[0].text


    @property
    def content(self):
        el = self.xpath('a:content')
        if not el:
            return (None, None)
        el = el[0]
        return (
            el.attrib.get('type', 'text'),
            (el.text and el.text.strip() or None)
        )


    @property
    def updated(self):
        updated = self.xpath('a:updated')[0].text
        return datetime.datetime.strptime(
            updated,
            '%Y-%m-%dT%H:%M:%SZ'
        )


    @property
    def link_url(self):
        url = self.xpath('y:meta/y:url')
        if url:
            return url[0].text
        return None


    def get_link(self, rel):
        el = self.xpath('a:link[@rel="%s"]' % rel)
        if el:
            return el[0].attrib['href']
        return ''


    def reply(self, message):
        self._api.comment_post(self.get_link('self'), message)



class YaRuAPI(object):
    def __init__(self, token):
        self._AUTH_TOKEN = token



    @inlineCallbacks
    def _auth_request(self, url, body = None):
        '''Создаёт авторизованный объект запроса.'''
        try:
            data = yield client.getPage(
                force_str(url),
                method = body and 'POST' or 'GET',
                headers = {
                    'User-Agent': 'YaRu Jabber bot: http://yaru.svetlyak.ru',
                    'Authorization': force_str('OAuth %s' % self._AUTH_TOKEN),
                },
                postdata = force_str(body),
            )
            returnValue(data)
        except WebError, e:
            message = u'ERROR: YaRuAPI (%s) url="%s", body="%s"' % (
                unicode(e), url, body
            )
            log.msg(message.encode('utf-8'))
            if int(e.status) == 401:
                raise InvalidAuthToken(e)
            raise


    @inlineCallbacks
    def _get_link(self, rel):
        '''Возвращает URL нужного ресурса из профиля авторизованного пользователя.'''
        f = yield self._auth_request('%s/me/' % HOST)
        xml = ET.fromstring(f)
        links = xml.xpath('/y:person/y:link[@rel="%s"]' % rel, namespaces = NAMESPACES)
        returnValue(links[0].attrib['href'])


    @inlineCallbacks
    def get_friend_feed(self):
        posts_link = yield self._get_link('friends_posts')
        posts = yield self._auth_request(posts_link)

        posts = ET.fromstring(posts)

        from_ = None

        posts = posts.xpath('a:entry', namespaces = NAMESPACES)
        posts = [Post(post, self) for post in posts]
        returnValue(posts)


    @inlineCallbacks
    def comment_post(self, post_url, message):
        url = post_url + '/comment/'
        el = ET.Element('{%(a)s}entry' % NAMESPACES)
        ET.SubElement(el, '{%(a)s}content' % NAMESPACES).text = message
        try:
            yield self._auth_request(url, ET.tostring(el))
        except WebError, e:
            if int(e.status) != 201:
                raise


    @inlineCallbacks
    def post_text(self, title = None, text = None):
        url = yield self._get_link('posts')

        el = ET.Element('{%(a)s}entry' % NAMESPACES)

        if title:
            ET.SubElement(el, '{%(a)s}title' % NAMESPACES).text = title

        if text:
            ET.SubElement(el, '{%(a)s}content' % NAMESPACES).text = text
        else: # TODO: Убрать, так как временная мера, пока в API не починят добавление постов без content
            ET.SubElement(el, '{%(a)s}content' % NAMESPACES).text = u'…'

        ET.SubElement(
            el, '{%(a)s}category' % NAMESPACES,
            scheme = 'urn:ya.ru:posttypes', term = 'text'
        )
        try:
            result = yield self._auth_request(url, ET.tostring(el))
        except WebError, e:
            if int(e.status) != 201:
                raise

        result = ET.fromstring(result.decode('utf-8'))
        links = result.xpath('a:link[@rel = "alternate"]', namespaces = NAMESPACES)
        if len(links) != 0:
            returnValue(links[0].attrib['href'])


    @inlineCallbacks
    def post_link(self, url, title = None, comment = None):
        posts_url = yield self._get_link('posts')

        el = ET.Element('{%(a)s}entry' % NAMESPACES)

        if title:
            ET.SubElement(el, '{%(a)s}title' % NAMESPACES).text = title

        if comment:
            ET.SubElement(el, '{%(a)s}content' % NAMESPACES).text = comment
        else:
            ET.SubElement(el, '{%(a)s}content' % NAMESPACES)

        meta = ET.SubElement(el, '{%(y)s}meta' % NAMESPACES)
        ET.SubElement(meta, '{%(y)s}url' % NAMESPACES).text = url

        ET.SubElement(
            el, '{%(a)s}category' % NAMESPACES,
            scheme = 'urn:ya.ru:posttypes', term = 'link'
        )

        try:
            result = yield self._auth_request(posts_url, ET.tostring(el))
        except WebError, e:
            if int(e.status) != 201:
                raise

        result = ET.fromstring(result.decode('utf-8'))
        links = result.xpath('a:link[@rel = "alternate"]', namespaces = NAMESPACES)
        if len(links) != 0:
            returnValue(links[0].attrib['href'])

