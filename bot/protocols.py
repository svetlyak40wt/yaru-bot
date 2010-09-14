# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

import datetime
import os.path
import pickle
import re

from functools import wraps
from . import messages, db, stats
from . models import User
from . api import YaRuAPI, ET
from . scheduler import POSTS_DEBUG_CACHE
from pdb import set_trace
from twisted.internet.defer import inlineCallbacks, returnValue, succeed, CancelledError
from twisted.internet import reactor
from twisted.internet.task import deferLater
from twisted.python.failure import Failure
from twisted.python import log
from twisted.words.protocols.jabber.jid import JID
from twisted.words.xish import domish
from wokkel import disco
from wokkel import xmppim
from wokkel.iwokkel import IDisco
from zope.interface import implements


CHATSTATE_NS = 'http://jabber.org/protocol/chatstates'
POST_DELAY = 15


def _get_fragment(text):
    if len(text) > 20:
        return text[:20] + u'…'
    return text


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
        if request.jid.userhost() not in self._get_admins():
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
    def _cmd_reply(self, request, dyn_id = None, text = None):
        dyn_id = int(dyn_id)
        post_url = request.user.get_post_url_by_id(dyn_id)

        if post_url is None:
            self.send_plain(request.jid.full(), u'Пост #%0.2d не найден' % dyn_id)
        else:
            fragment = _get_fragment(text)

            @inlineCallbacks
            def _comment(user_jid, post_url, auth_token, text):
                api = YaRuAPI(auth_token)
                yield api.comment_post(post_url, text)
                self.send_plain(user_jid, u'Комментарий "%s" добавлен' % fragment)
                stats.STATS['sent_comments'] += 1

            task = deferLater(
                reactor, POST_DELAY, _comment,
                request.jid.full(),
                post_url,
                request.user.auth_token,
                text
            )
            self._delayed_command_end(
                request, task,
                u'Комментарий будет добавлен через %(delay)d секунд. Напиши "отмена" если передумал.',
                u'Коментарий "%s" отменен' % fragment
            )


    def _delayed_command_end(self, request, task, success_message, cancel_message):
        """ Добавляет обработчик отмены поста/коммента, и выводит предупреждение о том,
            что действие будет совершено не сразу, и его можно отменить.
        """
        def eb(result):
            if isinstance(result.value, CancelledError):
                self.send_plain(request.jid.full(), cancel_message)

        task.addErrback(eb)
        request.user.add_delayed_task(task)
        self.send_plain(
            request.jid.full(),
            success_message % dict(delay = POST_DELAY)
        )


    @require_auth_token
    def _cmd_post_text(self, request, text = None):
        fragment = _get_fragment(text)

        @inlineCallbacks
        def _post(user_jid, auth_token):
            api = YaRuAPI(auth_token)
            post_url = yield api.post_text(text)
            self.send_plain(user_jid, u'Пост "%s" добавлен: %s' % (fragment, post_url))
            stats.STATS['sent_posts'] += 1

        task = deferLater(
            reactor, POST_DELAY, _post,
            request.jid.full(),
            request.user.auth_token,
        )
        self._delayed_command_end(
            request, task,
            u'Пост будет добавлен через %(delay)d секунд. Напиши "отмена" если передумал.',
            u'Публикация поста "%s" отменена' % fragment
        )


    @require_auth_token
    def _cmd_post_link(self, request, url = None, title = None, comment = None):
        # Боремся против iChat, который присылает url как http://ya.ru [http://ya.ru]
        url = url.split(' ', 1)[0]

        @inlineCallbacks
        def _post(user_jid, auth_token):
            api = YaRuAPI(auth_token)
            post_url = yield api.post_link(url, title, comment)
            self.send_plain(user_jid, u'Ссылка "%s" добавлена: %s' % (url, post_url))
            stats.STATS['sent_links'] += 1

        task = deferLater(
            reactor, POST_DELAY, _post,
            request.jid.full(),
            request.user.auth_token,
        )
        self._delayed_command_end(
            request, task,
            u'Ссылка будет добавлена через %(delay)d секунд. Напиши "отмена" если передумал.',
            u'Публикация ссылки "%s" отменена' % url
        )


    @require_auth_token
    def _cmd_cancel(self, request):
        canceled = request.user.cancel_delayed_tasks()
        if canceled == 0:
            self.send_plain(request.jid.full(), u'Нечего отменять')



    @require_auth_token
    @inlineCallbacks
    # TODO подумать что делать с этой командой
    def _cmd_forget_post(self, request, dyn_id = None):
        dyn_id = int(dyn_id)
        post_url = request.user.get_post_url_by_id(dyn_id)

        if post_url is None:
            self.send_plain(request.jid.full(), u'Пост %0.2d не найден' % dyn_id)
        else:
            # TODO вот здесь надо что-то другое придумать
            yield request.user.unregister_id(dyn_id)
            self.send_plain(request.jid.full(), u'Слушаю и повинуюсь!')


    @admin_only
    def _cmd_show_xml(self, request, dyn_id = None):
        dyn_id = int(dyn_id)
        post = POSTS_DEBUG_CACHE.get((request.user.id, dyn_id))

        if post is None:
            self.send_plain(request.jid.full(), u'Пост %0.2d не найден' % dyn_id)
        else:
            self.send_plain(request.jid.full(), u'Пост %0.2d:\r\n%s' % (dyn_id, ET.tostring(post._xml)))


    @admin_only
    @inlineCallbacks
    def _cmd_announce(self, request, text = None):
        users = yield self._get_active_users(request.store)

        text = u'Анонс: ' + text

        for user in users:
            self.send_plain(user.jid, text)

        self.send_plain(request.jid.full(), u'Анонс разослан')


    @require_auth_token
    def _cmd_on(self, request):
        request.user.off = False
        self.send_plain(request.jid.full(), u'Хорошо, давай ка проверим чего там тебе понаписали!')


    @require_auth_token
    def _cmd_off(self, request):
        request.user.off = True
        self.send_plain(
            request.jid.full(),
            u'Как пожелаешь, мой господин, больше не будут тебя спамить!\n'
            u'Когда освободишься, используй команду "вкл", чтобы включить меня обратно.'
        )


    @require_auth_token
    def _cmd_status(self, request):
        if request.user.off:
            self.send_plain(request.jid.full(), u'Проверка фредленты отключена')
        else:
            self.send_plain(request.jid.full(), u'Выполняется проверка френдленты')


    _COMMANDS = (
        ((u'help', u'помощь', u'справка', u'помоги .*'), _cmd_help),
        ((
            ur'#(?P<dyn_id>[0-9]+) (?P<text>.*)',
            ur'№(?P<dyn_id>[0-9]+) (?P<text>.*)',
         ), _cmd_reply),
        ((ur'on', ur'вкл'), _cmd_on),
        ((ur'off', ur'выкл'), _cmd_off),
        ((ur'status', ur'статус'), _cmd_status),
        ((ur'post (?P<text>.*)', ur'пост (?P<text>.*)'), _cmd_post_text),
        ((
            ur'link (?P<url>.+?) - (?P<title>.+?) - (?P<comment>.+)',
            ur'ссылка (?P<url>.+?) - (?P<title>.+?) - (?P<comment>.+)',
            ur'link (?P<url>.+?) - (?P<title>.+)',
            ur'ссылка (?P<url>.+?) - (?P<title>.+)',
            ur'link (?P<url>.+)',
            ur'ссылка (?P<url>.+)',
         ), _cmd_post_link),
        ((ur'cancel', ur'отменить', ur'отмена', ur'ой', ur'упс', ur'бля'), _cmd_cancel),
        ((ur'/f (?P<dyn_id>[0-9]+)',), _cmd_forget_post),
        ((ur'/xml (?P<dyn_id>[0-9]+)',), _cmd_show_xml),
        ((ur'/announce (?P<text>.*)', ur'/анонс (?P<text>.*)'), _cmd_announce),
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

            for a in self._get_admins():
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

    def _get_admins(self):
        return self.cfg['bot'].get('admins', [])



class MessageProtocol(xmppim.MessageProtocol, MessageCreatorMixIn, CommandsMixIn, HelpersMixIn):
    implements(IDisco)

    def __init__(self, cfg):
        self.jid = cfg['bot']['jid']
        self.client_id = cfg['api']['client_id']
        self.cfg = cfg
        super(MessageProtocol, self).__init__()


    def onMessage(self, msg):
        log.msg('onMessage call: type=%r, body=%r' % (msg.getAttribute('type'), msg.body))
        if msg.getAttribute('type') == 'chat' and hasattr(msg, 'body') and msg.body:
            request = Request(msg, self.client_id)
            command = unicode(msg.body)

            if command == 'pdb' and \
                    request.jid.userhost() in self._get_admins():
                set_trace()


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

