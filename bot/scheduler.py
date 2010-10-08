# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

import datetime

from . api import YaRuAPI, InvalidAuthToken, ET
from . import db
from . import stats
from . import log
from . models import User, DynamicID
from . renderer import render
from twisted.internet import reactor, defer
from twisted.internet.defer import inlineCallbacks
from twisted.web.error import Error as WebError

POSTS_DEBUG_CACHE = {}

check_sem = None
init_sem = defer.DeferredSemaphore(tokens = 1)
bot = None
reschedule_interval = 120

class Processor(set):
    def __init__(self, short_jid, loop_time = None, token = None):
        self.short_jid = short_jid
        self.loop_time = loop_time or reschedule_interval
        self.loop = None
        self.token = token
        self.status = None
        self.off = False
        self.task = None # Отложенная задача по проверке постов


    @inlineCallbacks
    def __call__(self):
        self.status = 'in-progress'
        try:
            if self.token and not self.off and len(self):
                yield db.pool.transact(self._process_posts)
        except Exception, e:
            log.err(None, 'ERROR during retriving posts for "%s"' % self.short_jid)
        self.status = None
        self._reschedule()


    @inlineCallbacks
    def _process_posts(self, store):
        log.msg('Retriving posts from yaru for: %s' % self.short_jid)
        query = yield store.find(
            User,
            User.jid == self.short_jid
        )
        user = yield query.one()

        try:
            api = YaRuAPI(user.auth_token)
            posts = yield api.get_friend_feed()
        except WebError, e:
            log.err(None, 'ERROR in process_user_posts')
        except InvalidAuthToken:
            self.token = None
            user.auth_token = None
            user.refresh_token = None
            user.updated_at = datetime.datetime.utcnow()
            stats.STATS['unsubscribed'] += 1
        else:

            start_from = user.last_post_at
            if start_from is None:
                if posts:
                    start_from = posts[0].updated - datetime.timedelta(0, 1)
                else:
                    start_from = datetime.datetime.utcnow()

            retried_posts = User._retried_posts[user.id]

            for post in reversed(posts):
                post_link = unicode(post.get_link('self'))

                if post.updated > start_from or post_link in retried_posts:
                    try:
                        dyn_id = None
                        dyn_id = yield user.register_url(post_link)

                        message, html_message = render(dyn_id.id, post)

                        log.msg((u'User %s, post %s: %s' % (user.jid, dyn_id.id, html_message)).encode('utf-8'))

                        for jid in self:
                            bot.send_html(jid, message, html_message)

                        POSTS_DEBUG_CACHE[(user.id, dyn_id.id)] = post
                        stats.STATS['posts_processed'] += 1
                        user.last_post_at = post.updated

                        retried_posts.discard(post_link)

                    except Exception, e:
                        log.err(None, 'ERROR in post processing for %s: %s' % (
                                user.jid,
                                ET.tostring(post._xml)
                            )
                        )
                        stats.STATS['posts_processed'] -= 1
                        stats.STATS['posts_failed'] += 1
                        yield user.unregister_id(dyn_id)
                        break

            yield store.flush()


    def _reschedule(self):
        params = [
            self.short_jid,
            self.status,
            self.token,
        ]
        if self.status is None and self.token:
            next_check_at = datetime.datetime.now() + datetime.timedelta(0, self.loop_time)
            params.append(next_check_at)
            log.msg('Reschedule for jid=%s, status=%s, token=%s: %s' % tuple(params))
            self.status = 'scheduled'

            self.task = reactor.callLater(self.loop_time, check_sem.run, self)
        else:
            log.msg('Pass reschedule for jid=%s, status=%s, token=%s' % tuple(params))


    def set_token(self, token):
        self.token = token
        self._reschedule()


    def add(self, jid):
        super(Processor, self).add(jid)
        self._reschedule()


    def discard(self, full_jid):
        super(Processor, self).discard(full_jid)
        if len(self) == 0:
            log.msg('No full jids for %s, deactivating scheduler for this user.' % self.short_jid)
            if self.task and self.task.active():
                self.status = None
                self.task.cancel()



class Processors(object):
    def __init__(self):
        self.processors = {}


    def add(self, short_jid, full_jid, token = None):
        log.msg('Adding %s as %s' % (short_jid, full_jid))

        if short_jid not in self.processors:
            self.processors[short_jid] = Processor(short_jid, token = token)
        else:
            self.processors[short_jid].set_token(token)
        self.processors[short_jid].add(full_jid)


    def remove(self, short_jid, full_jid = None):
        u = self.processors.get(short_jid)
        if u:
            u.discard(full_jid)


    def set_token(self, short_jid, token):
        u = self.processors.get(short_jid)
        if u:
            u.set_token(token)
        else:
            log.msg('Couldn\'t find %s to set token' % short_jid)


    def set_off(self, short_jid, off):
        u = self.processors.get(short_jid)
        if u:
            if off:
                log.msg('Disabling check for "%s"' % short_jid)
            else:
                log.msg('Enabling check for "%s"' % short_jid)

            u.off = off
        else:
            log.msg('Couldn\'t find %s to set token' % short_jid)


processors = Processors()


def _entity_to_jid(entity):
    return entity if isinstance(entity, basestring) else entity.userhost()


def __init_user(entity, jids=[]):
    jid = _entity_to_jid(entity)

    @inlineCallbacks
    def process_user(store):
        results = yield store.find(
            User,
            User.jid == jid,
            User.subscribed == True,
            User.auth_token != None,
        )
        user = yield results.one()
        if user:
            for j in jids:
                processors.add(jid, j, token = user.auth_token)
            processors.set_off(jid, user.off)

    db.pool.transact(process_user)


def available_user(entity):
    init_sem.run(__init_user, entity, [entity.full()])


def unavailable_user(entity):
    processors.remove(entity.userhost(), entity.full())


def init(config, _bot):
    global bot, check_sem, reschedule_interval
    bot = _bot
    check_sem = defer.DeferredSemaphore(tokens = config.get('num_users_in_batch', 5))
    reschedule_interval = config.get('reschedule_interval', reschedule_interval)

    # кэшируем запомненные ссылки
    @inlineCallbacks
    def load_ids(store):
        results = yield store.find(DynamicID)
        results = yield results.all()

        for dyn_id in results:
            User._ids_cache[dyn_id.user_id][dyn_id.id] = dyn_id.url

    db.pool.transact(load_ids)

