# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

from . api import YaRuAPI, InvalidAuthToken
from . import db
from . models import User, PostLink
from . renderer import render
from pdb import set_trace
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

POSTS_DEBUG_CACHE = {}

class Scheduler(object):
    def __init__(self, config, bot):
        self.cfg = config
        self.bot = bot


        # кэшируем уже полученные посты
        @inlineCallbacks
        def load_posts(store):
            results = yield store.find(PostLink)
            results.order_by(PostLink.user_id)
            results = yield results.all()

            user_id = None
            user_posts = {}
            user_hashes = {}

            for post in results:
                if post.user_id != user_id:
                    if user_id is not None:
                        User._posts_cache[user_id] = user_posts
                        User._hash_cache[user_id] = user_hashes
                    user_id = post.user_id
                    user_posts = {}
                    user_hashes = {}
                user_posts[post.url] = True
                user_hashes[post.hash] = post.url

            if user_id is not None:
                User._posts_cache[user_id] = user_posts
                User._hash_cache[user_id] = user_hashes
        db.pool.transact(load_posts)



    def process_new_posts(self):
        # цикл проверки постов в ярушке
        @inlineCallbacks
        def process_user_posts(store, user):
            user.attach(store)
            try:
                api = YaRuAPI(user.auth_token)

                posts = yield api.get_friend_feed()

                for post in posts:
                    post_date = post.updated
                    post_link = unicode(post.get_link('self'))

                    registered = user.is_post_registered(post_link)
                    if registered:
                        #log.msg('ignoring "%s"' % post_link)
                        # не показываем посты которые уже были показаны
                        continue

                    post_link = yield user.register_post(post_link)
                    POSTS_DEBUG_CACHE[post_link.hash] = post

                    message, html_message = render(post_link.hash, post)

                    log.msg('Post %s: %s' % (post_link.hash.encode('utf-8'), html_message.encode('utf-8')))
                    self.bot.send_html(user.jid, message, html_message)
            except InvalidAuthToken:
                user.auth_token = None
                user.refresh_token = None
                yield store.flush()


        @inlineCallbacks
        def process_users(store):
            results = yield store.find(User, User.subscribed == True, User.auth_token != None)
            users = yield results.all()

            for user in users:
                log.msg('Retriving posts from yaru for: %s' % user.jid)
                db.pool.transact(process_user_posts, user.detach())

        db.pool.transact(process_users)

