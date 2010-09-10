# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

import datetime

from . api import YaRuAPI, InvalidAuthToken, ET
from . import db
from . import stats
from . models import User, DynamicID
from . renderer import render
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

POSTS_DEBUG_CACHE = {}

class Scheduler(object):
    def __init__(self, config, bot):
        self.bot = bot
        self.num_users_in_batch = config.get('num_users_in_batch', 5)
        self.reschedule_interval = config.get('reschedule_interval', 120)


        # кэшируем запомненные ссылки
        @inlineCallbacks
        def load_ids(store):
            results = yield store.find(DynamicID)
            results = yield results.all()

            for dyn_id in results:
                User._ids_cache[dyn_id.user_id][dyn_id.id] = dyn_id.url

        db.pool.transact(load_ids)



    def process_new_posts(self):
        # цикл проверки постов в ярушке
        @inlineCallbacks
        def process_user_posts(store, user):
            user.attach(store)
            try:
                api = YaRuAPI(user.auth_token)
                posts = yield api.get_friend_feed()
            except InvalidAuthToken:
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

                for post in posts:
                    if post.updated > start_from:
                        try:
                            post_link = unicode(post.get_link('self'))
                            dyn_id = None
                            dyn_id = yield user.register_url(post_link)

                            message, html_message = render(dyn_id.id, post)

                            log.msg((u'User %s, post %s: %s' % (user.jid, dyn_id.id, html_message)).encode('utf-8'))
                            self.bot.send_html(user.jid, message, html_message)

                            POSTS_DEBUG_CACHE[(user.id, dyn_id.id)] = post
                            stats.STATS['posts_processed'] += 1
                            user.last_post_at = post.updated

                        except Exception, e:
                            log.msg('ERROR in post processing for %s: %s' % (
                                    user.jid,
                                    ET.tostring(post._xml)
                                )
                            )
                            log.err()
                            stats.STATS['posts_processed'] -= 1
                            stats.STATS['posts_failed'] += 1
                            yield user.unregister_id(dyn_id)
                            break

            user.next_poll_at = \
                datetime.datetime.utcnow() + \
                datetime.timedelta(0, self.reschedule_interval)
            yield store.flush()


        @inlineCallbacks
        def process_users(store):
            now = datetime.datetime.utcnow()
            results = yield store.find(
                User,
                User.subscribed == True,
                User.auth_token != None,
                User.next_poll_at < now,
            )
            results.order_by(User.next_poll_at)
            results.config(limit = self.num_users_in_batch)
            users = yield results.all()

            for user in users:
                log.msg('Retriving posts from yaru for: %s' % user.jid)
                db.pool.transact(process_user_posts, user.detach())

        db.pool.transact(process_users)

