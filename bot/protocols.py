# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

import datetime
import os.path
import pickle
import re

from functools import wraps
from . import messages, db
from . models import User, PostLink
from . api import YaRuAPI, comment_post, ET
from . scheduler import POSTS_DEBUG_CACHE
from pdb import set_trace
from twisted.internet.defer import inlineCallbacks, returnValue, succeed
from twisted.python.failure import Failure
from twisted.python import log
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish
from wokkel import disco
from wokkel import xmppim
from wokkel.iwokkel import IDisco
from zope.interface import implements


CHATSTATE_NS = 'http://jabber.org/protocol/chatstates'


class Request(object):
    def __init__(self, message, client_id):
        self.message = message
        self.jid = JID(message['from'])
        self.client_id = client_id



class MessageCreatorMixIn(object):
    """ MixIn to send plain text and HTML messages. """
    def _create_message(self):
        msg = domish.Element((None, 'message'))
        import time
        msg['id'] = str(time.time())
        msg.addElement((CHATSTATE_NS, 'active'))
        return msg


    def send_plain(self, jid, content):
        msg = self._create_message()
        msg['to'] = jid
        msg['from'] = self.jid
        msg['type'] = 'chat'
        msg.addElement('body', content = content)

        self.send(msg)


    def send_html(self, jid, body, html):
        msg = self._create_message()
        msg['to'] = jid
        msg['from'] = self.jid
        msg['type'] = 'chat'
        html = u'<html xmlns="http://jabber.org/protocol/xhtml-im"><body xmlns="http://www.w3.org/1999/xhtml">' + unicode(html) + u'</body></html>'
        msg.addRawXml(u'<body>' + unicode(body) + u'</body>')
        msg.addRawXml(unicode(html))

        self.send(msg)



def require_auth_token(func):
    """ Декоратор, который требует, чтобы о пользователе
        были известны его яндекс-логин и авторизационный
        токен.
    """
    @wraps(func)
    def wrapper(self, request, **kwargs):
        if not request.user.auth_token:
            self.send_plain(
                request.jid.full(),
                messages.REQUIRE_AUTH_TOKEN % (
                    request.client_id, request.jid.userhost()
                )
            )
        else:
            return func(self, request, **kwargs)
    return wrapper



def admin_only(func):
    """ Декоратор, который требует, чтобы о пользователе
        были известны его яндекс-логин и авторизационный
        токен.
    """
    @wraps(func)
    def wrapper(self, request, **kwargs):
        admins = self.cfg['bot'].get('admins', [])

        if request.jid.userhost() not in admins:
            self.send_plain(
                request.jid.full(),
                messages.REQUIRE_BE_ADMIN
            )
        else:
            return func(self, request, **kwargs)
    return wrapper




class CommandsMixIn(object):
    """ Всевозможные команды, которые бот умеет понимать. """
    def _get_command(self, text):
        for aliases, func in CommandsMixIn._COMMANDS:
            for alias in aliases:
                match = alias.match(text)
                if match is not None:
                    return (
                        func,
                        dict((str(key), value) for key, value in match.groupdict().items())
                    )
        return None, None


    @require_auth_token
    def _cmd_help(self, request):
        self.send_plain(request.jid.full(), messages.HELP)


    @require_auth_token
    @inlineCallbacks
    def _cmd_reply(self, request, hash = None, text = None):
        post_url = request.user.get_post_url_by_hash(hash)

        if post_url is None:
            self.send_plain(request.jid.full(), u'Пост #%s не найден' % hash)
        else:
            api = YaRuAPI(request.user.auth_token)
            yield comment_post(api, post_url, text)
            self.send_plain(request.jid.full(), u'Комментарий добавлен')



    @require_auth_token
    @inlineCallbacks
    def _cmd_forget_post(self, request, hash = None):
        post_url = request.user.get_post_url_by_hash(hash)

        if post_url is None:
            self.send_plain(request.jid.full(), u'Пост %s не найден' % hash)
        else:
            yield request.user.unregister_post(hash)
            self.send_plain(request.jid.full(), u'Слушаю и повинуюсь!')


    @admin_only
    def _cmd_show_xml(self, request, hash = None):
        post = POSTS_DEBUG_CACHE.get(hash)

        if post is None:
            self.send_plain(request.jid.full(), u'Пост %s не найден' % hash)
        else:
            self.send_plain(request.jid.full(), u'Пост %s:\r\n%s' % (hash, ET.tostring(post._xml)))


    @admin_only
    @inlineCallbacks
    def _cmd_announce(self, request, text = None):
        users = yield self._get_active_users(request.store)

        text = u'Анонс: ' + text

        for user in users:
            self.send_plain(request.jid.full(), text)

        self.send_plain(request.jid.full(), u'Анонс разослан')



    _COMMANDS = (
        (('help', u'помощь', u'справка'), _cmd_help),
        ((r'#(?P<hash>[a-z0-9]+) (?P<text>.*)',), _cmd_reply),
        ((r'/f (?P<hash>[a-z0-9]+)',), _cmd_forget_post),
        ((r'/xml (?P<hash>[a-z0-9]+)',), _cmd_show_xml),
        ((r'/announce (?P<text>.*)', ur'/анонс (?P<text>.*)'), _cmd_announce),
    )
    _COMMANDS =  tuple(
        (tuple(re.compile(alias) for alias in aliases), func)
        for aliases, func in _COMMANDS
    )



class HelpersMixIn(object):
    @inlineCallbacks
    def _get_or_create_user(self, store, jid):
        user = yield store.find(User, User.jid == jid.userhost())
        user = yield user.one()
        created = False

        if user is None:
            created = True
            user = User(jid = jid.userhost())
            yield store.add(user)

            msg = u'Новый подписчик: %s' % jid.userhost()

            admins = self.cfg['bot'].get('admins', [])

            for a in admins:
                self.send_plain(a, msg)

            self.send_plain(
                jid.full(),
                messages.NEW_USER_WELCOME % (
                    self.client_id, jid.userhost()
                )
            )
        returnValue((user, created))


    @inlineCallbacks
    def _get_active_users(self, store):
        users = yield store.find(
            User,
            User.subscribed == True,
            User.auth_token != None,
        )
        users = yield users.all()
        returnValue(users)



class MessageProtocol(xmppim.MessageProtocol, MessageCreatorMixIn, CommandsMixIn, HelpersMixIn):
    implements(IDisco)

    def __init__(self, cfg):
        self.jid = cfg['bot']['jid']
        self.client_id = cfg['api']['client_id']
        self.cfg = cfg
        super(MessageProtocol, self).__init__()


    def onMessage(self, msg):
        log.msg('onMessage call: type=%r, body=%r' % (msg.getAttribute('type'), msg.body))
        if msg.getAttribute('type') == 'chat' and unicode(msg.body) == 'pdb':
            log.msg('making set_trace')
            set_trace()

        if msg.getAttribute('type') == 'chat' and hasattr(msg, 'body') and msg.body:
            request = Request(msg, self.client_id)
            command = unicode(msg.body)

            @inlineCallbacks
            def _process_request(store):
                user, created = yield self._get_or_create_user(store, request.jid)
                request.user = user
                request.store = store

                func, kwargs = self._get_command(command)

                if func is not None:
                    try:
                        yield func(self, request, **kwargs)
                    except Exception, e:
                        log.err()
                        self.send_plain(request.jid.full(), u'Ошибка: %s' % e)
                        raise
                else:
                    self.send_plain(request.jid.full(), u'Нет такой команды (см. help).')

            db.pool.transact(_process_request)


    def getDiscoInfo(self, requestor, target, node):
        info = set()
        if not node:
            info.add(disco.DiscoFeature('http://jabber.org/protocol/xhtml-im'))
        return succeed(info)

    def getDiscoItems(self, requestor, target, node):
        return succeed([])



class PresenceProtocol(xmppim.PresenceClientProtocol, MessageCreatorMixIn, HelpersMixIn):
    def __init__(self, cfg):
        self.jid = cfg['bot']['jid']
        self.cfg = cfg
        self.client_id = cfg['api']['client_id']
        super(PresenceProtocol, self).__init__()


    def connectionInitialized(self):
        super(PresenceProtocol, self).connectionInitialized()
        self.update_presence()


    def subscribeReceived(self, entity):
        log.msg('Subscribe received from %s' % (entity.userhost()))
        self.subscribe(entity)
        self.subscribed(entity)
        self.update_presence()


    def subscribedReceived(self, entity):
        log.msg('Subscribe received from %s' % (entity.userhost()))

        @inlineCallbacks
        def _add_user(store):
            user, created = yield self._get_or_create_user(store, entity)
            user.subscribed = True

            if not created:
                self.send_plain(entity.full(), messages.OLD_USER_WELCOME)

        db.pool.transact(_add_user)


    def unsubscribeReceived(self, entity):
        log.msg('Unsubscribe received from %s' % (entity.userhost()))

        @inlineCallbacks
        def _unsubscribe_user(store):
            user = yield store.find(User, User.jid == entity.userhost())
            user = yield user.one

            if user is not None:
                user.subscribed = False
                store.add(user)
        db.pool.transact(_unsubscribe_user)


        self.unsubscribe(entity)
        self.unsubscribed(entity)
        self.update_presence()


    def update_presence(self):
        status = u'Мир, Дружба, Ярушка!'
        self.available(None, None, {None: status})

