# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

import datetime
import os.path
import pickle
import re

from functools import wraps
from . import messages, db
from . models import User
from pdb import set_trace
from twisted.python.failure import Failure
from twisted.python import log
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish
from wokkel import xmppim


CHATSTATE_NS = 'http://jabber.org/protocol/chatstates'


class Request(object):
    def __init__(self, message):
        self.message = message
        self.jid = JID(message['from'])



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
            self.send_plain(request.jid.full(), messages.REQUIRE_AUTH_TOKEN % request.jid.userhost())
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
    def _cmd_reply(self, request, hash = None, text = None):
        if hash in self.posts:
            post = self.posts[hash]
            post.reply(request.message)
        else:
            self.send_plain(request.jid.full(), u'Пост #%s не найден' % hash)



    _COMMANDS = (
        (('help', u'помощь', 'справка'), _cmd_help),
        ((r'#(?P<hash>[a-z0-9]{2}) (?P<text>.*)',), _cmd_reply),
    )
    _COMMANDS =  tuple(
        (tuple(re.compile(alias) for alias in aliases), func)
        for aliases, func in _COMMANDS
    )



class MessageProtocol(xmppim.MessageProtocol, MessageCreatorMixIn, CommandsMixIn):
    def __init__(self, cfg):
        super(MessageProtocol, self).__init__()
        self.jid = cfg['bot']['jid']
        self.cfg = cfg


    def onMessage(self, msg):
        if msg['type'] == 'chat' and hasattr(msg, 'body') and msg.body:
            request = Request(msg)
            command = unicode(msg.body)

            def _process_request(user):
                if user is None:
                    user = User(jid = request.jid.userhost())
                    db.store.add(user)
                    db.store.commit()

                request.user = user

                func, kwargs = self._get_command(command)

                if func is not None:
                    func(self, request, **kwargs)

            db.store.find(User, User.jid == request.jid.userhost())\
                .addCallback(lambda r: r.one().addCallback(_process_request))



class PresenceProtocol(xmppim.PresenceClientProtocol, MessageCreatorMixIn):
    def __init__(self, cfg):
        super(PresenceProtocol, self).__init__()
        self.jid = cfg['bot']['jid']
        self.admins = cfg['bot'].get('admins', [])
        self.cfg = cfg


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

        def _user_found(user):
            if user is None:
                def _user_added(result):
                    msg = u'Новый подписчик: %s' % entity.userhost()

                    for a in self.admins:
                        self.send_plain(a, msg)
                    self.send_plain(entity.full(), messages.NEW_USER_WELCOME % entity.userhost())

                user = User(jid = entity.userhost())
                db.store.add(user)
                db.store.commit().addCallback(_user_added)

            else:
                user.subscribed = True
                db.store.add(user)
                db.store.commit()
                self.send_plain(entity.full(), messages.OLD_USER_WELCOME)


        db.store.find(User, User.jid == entity.userhost()) \
            .addCallback(lambda r: r.one().addCallback(_user_found))


    def unsubscribeReceived(self, entity):
        log.msg('Unsubscribe received from %s' % (entity.userhost()))
        def _user_found(user):
            if user is not None:
                user.subscribed = False
                db.store.add(user)
                db.store.commit()

        db.store.find(User, User.jid == entity.userhost()) \
            .addCallback(lambda r: r.one().addCallback(_user_found))

        self.unsubscribe(entity)
        self.unsubscribed(entity)
        self.update_presence()


    def update_presence(self):
        status = u'Мир, Дружба, Ярушка!'
        self.available(None, None, {None: status})

