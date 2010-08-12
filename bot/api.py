#!/usr/bin/env python
# -*- coding: utf-8 -*-

import urllib2
import datetime

from lxml import etree as ET
from pdb import set_trace

NAMESPACES = {
  'a': 'http://www.w3.org/2005/Atom',
  'y': 'yandex:data',
}

HOST = 'api-yaru.yandex.ru'



class Post(object):
    def __init__(self, xml, api):
        self._xml = xml
        self._api = api


    def __getstate__(self):
        return (ET.tostring(self._xml), self._api)


    def __setstate__(self, state):
        self._xml = ET.fromstring(state[0])
        self._api = state[1]


    @property
    def post_type(self):
        return self._xml.xpath(
            'a:category[@scheme = "urn:ya.ru:posttypes"]',
            namespaces = NAMESPACES
        )[0].attrib['term']

    @property
    def author(self):
        return self._xml.xpath(
            'a:author/a:name',
            namespaces = NAMESPACES
        )[0].text


    @property
    def title(self):
        return self._xml.xpath(
            'a:title',
            namespaces = NAMESPACES
        )[0].text


    @property
    def content(self):
        el = self._xml.xpath('a:content', namespaces = NAMESPACES)
        if not el:
            return (None, None)
        el = el[0]
        return (
            el.attrib.get('type', 'text'),
            (el.text and el.text.strip() or None)
        )



    @property
    def updated(self):
        updated = self._xml.xpath(
            'a:updated',
            namespaces = NAMESPACES
        )[0].text
        return datetime.datetime.strptime(
            updated,
            '%Y-%m-%dT%H:%M:%SZ'
        )


    def get_link(self, rel):
        el = self._xml.xpath(
            'a:link[@rel="%s"]' % rel,
            namespaces = NAMESPACES
        )
        if el:
            return el[0].attrib['href']
        return ''


    def reply(self, message):
        url = self.get_link('self') + '/comment/'
        el = ET.Element('{%(a)s}entry' % NAMESPACES)
        ET.SubElement(el, '{%(a)s}content' % NAMESPACES).text = message
        try:
            self._api._auth_request(url, ET.tostring(el))
        except urllib2.HTTPError, e:
            if e.code != 201:
                raise



class YaRuAPI(object):
    def __init__(self, token):
        self._ACCESS_TOKEN = token


    def _auth_request(self, url, body=None):
        '''Создаёт авторизованный объект запроса.'''
        return urllib2.urlopen(urllib2.Request(url, data=body, headers={
            'Authorization': 'OAuth %s' % self._ACCESS_TOKEN
        }))


    def _get_link(self, rel):
        '''Возвращает URL нужного ресурса из профиля авторизованного пользователя.'''
        f = self._auth_request('https://%s/me/' % HOST)
        xml = ET.parse(f)
        links = xml.xpath('/y:person/y:link[@rel="%s"]' % rel, namespaces = NAMESPACES)
        return links[0].attrib['href']


    def get_friend_feed(self):
#        posts = open('/tmp/friend-feed.xml', 'r').read()
        posts_link = self._get_link('friends_posts')
        posts = self._auth_request(posts_link).read()
        open('/tmp/friend-feed.xml', 'w').write(posts)

        posts = ET.fromstring(posts)

        from_ = None

        posts = posts.xpath('a:entry', namespaces = NAMESPACES)

        for post in posts:
            yield Post(post, self)

