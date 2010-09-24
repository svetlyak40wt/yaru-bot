# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

import re

from functools import wraps
from . import messages, db, stats, scheduler
from . models import User
from . api import YaRuAPI, ET
from pdb import set_trace
from twisted.internet.defer import inlineCallbacks, returnValue, succeed, CancelledError
from twisted.internet import reactor
from twisted.internet.task import deferLater
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
                u'Коментарий "%s" отменен' % fragment,
                u'Произошла ошибка, комментарий "%s" не добавлен' % fragment,
            )


    def _delayed_command_end(self, request, task, success_message, cancel_message, error_message):
        """ Добавляет обработчик отмены поста/коммента, и выводит предупреждение о том,
            что действие будет совершено не сразу, и его можно отменить.
        """
        def eb(result):
            if isinstance(result.value, CancelledError):
                self.send_plain(request.jid.full(), cancel_message)
            else:
                self.send_plain(request.jid.full(), error_message)
                message = u'ERROR: in delayed command (%s): %s' % (
                    unicode(result.value), request.message.toXml()
                )
                log.msg(message.encode('utf-8'))

        task.addErrback(eb)
        request.user.add_delayed_task(task)
        self.send_plain(
            request.jid.full(),
            success_message % dict(delay = POST_DELAY)
        )


    @require_auth_token
    def _cmd_post_text(self, request, text = None):
        # несложное преобразование текста
        # с целью выделить заголовок
        text = text.strip()
        lines = text.split('\n')
        num_lines = len(lines)
        if num_lines > 1:
            title = lines[0]
            text = '\n'.join(lines[1:])
        else:
            title = lines[0]
            if len(title) > 20:
                text = title
                title = title[:20] + u'…'
            else:
                text = None

        @inlineCallbacks
        def _post(user_jid, auth_token):
            api = YaRuAPI(auth_token)

            post_url = yield api.post_text(title = title, text = text)
            self.send_plain(user_jid, u'Пост "%s" добавлен: %s' % (title, post_url))
            stats.STATS['sent_posts'] += 1

        task = deferLater(
            reactor, POST_DELAY, _post,
            request.jid.full(),
            request.user.auth_token,
        )
        self._delayed_command_end(
            request, task,
            u'Пост будет опубликован через %(delay)d секунд. Напиши "отмена" если передумал.',
            u'Публикация поста "%s" отменена' % title,
            u'Произошла ошика, пост "%s" не опубликован' % title,
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
            u'Публикация ссылки "%s" отменена' % url,
            u'Произошла ошибка, ссылка "%s" не опубликована' % url,
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
        post = scheduler.POSTS_DEBUG_CACHE.get((request.user.id, dyn_id))

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
        scheduler.processors.set_off(request.jid.userhost(), request.user.off)

        self.send_plain(request.jid.full(), u'Хорошо, давай ка проверим чего там тебе понаписали!')


    @require_auth_token
    def _cmd_off(self, request):
        request.user.off = True
        scheduler.processors.set_off(request.jid.userhost(), request.user.off)

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
        (
            tuple(
                re.compile(alias, re.DOTALL | re.UNICODE | re.IGNORECASE)
                for alias in aliases
            ),
            func
        )
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


    def connectionInitialized(self):
        super(MessageProtocol, self).connectionInitialized()
        log.msg('MessageProtocol connected')
        self.connected = True


    def connectionLost(self, reason):
        super(MessageProtocol, self).connectionLost(reason)
        log.msg('MessageProtocol disconnected, reason: %s' % reason)
        self.connected = False


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
                        log.err(None, 'ERROR in _process_request')
                        self.send_plain(request.jid.full(), u'Ошибка: %s' % e)
                        raise
                else:
                    self.send_plain(request.jid.full(), u'Нет такой команды (см. help).')

            db.pool.transact(_process_request)


    def onError(self, msg):
        log.msg('ERROR received for %s: %s' % (msg['from'], msg.toXml()))
        scheduler.unavailable_user(JID(msg['from']))


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
        log.msg('PrecenceProtocol connected')
        self.update_presence()


    def connectionLost(self, reason):
        super(PresenceProtocol, self).connectionLost(reason)
        log.msg('PrecenceProtocol disconnected, reason: %s' % reason)


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


    def update_presence(self, recipient_jid = None):
        status = u'Мир, Дружба, Ярушка!'
        if isinstance(recipient_jid, basestring):
            recipient_jid = JID(recipient_jid)
        self.available(recipient_jid, None, {None: status})


    def probe(self, recipient, sender = None):
        presence = xmppim.ProbePresence(recipient = recipient, sender = sender)
        self.send(presence.toElement())


    def availableReceived(self, entity, show = None, statuses = None, priority = 0):
        log.msg((u'Available from %s (%s, %s, pri=%s)' % (
            entity.full(), show, statuses, priority)).encode('utf-8')
        )

        if priority >= 0 and show not in ['xa', 'dnd']:
            scheduler.available_user(entity)
        else:
            log.msg('Marking jid unavailable due to negative priority or '
                    'being somewhat unavailable.')
            scheduler.unavailable_user(entity)


    def unavailableReceived(self, entity, statuses=None):
        log.msg((u'Unavailable from %s' % entity.full()).encode('utf-8'))
        scheduler.unavailable_user(entity)

