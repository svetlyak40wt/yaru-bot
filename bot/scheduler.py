# -*- coding: utf-8 -*-
from __future__ import with_statement, absolute_import

from . api import YaRuAPI
from . import db
from . models import User, PostLink
from pdb import set_trace
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

class Scheduler(object):
    def __init__(self, config, bot):
        self.users = {}
        self.cfg = config
        self.bot = bot

        @inlineCallbacks
        def load_users(store):
            results = yield store.find(User, User.subscribed == True)
            results = yield results.all()

            for user in results:
                self.add(user)
        db.pool.transact(load_users)


        # кэшируем уже полученные посты
        @inlineCallbacks
        def load_posts(store):
            results = yield store.find(PostLink)
            results.order_by(PostLink.user_id)
            results = yield results.all()

            user_id = None
            user_posts = {}

            for post in results:
                if post.user_id != user_id:
                    if user_id is not None:
                        User._posts_cache[user_id] = user_posts
                    user_id = post.user_id
                    user_posts = {}
                user_posts[post.url] = True
        db.pool.transact(load_posts)



    def add(self, user):
        user.detach()
        self.users[user.jid] = user


    def remove(self, user):
        if user.jid in self.users:
            del self.users[user.jid]


    def process_new_posts(self):
        # цикл проверки постов в ярушке
        log.msg('Retriving posts from yaru.')

        @inlineCallbacks
        def process_user_posts(store, user):
            api = YaRuAPI(user.auth_token)

            for post in api.get_friend_feed():
                post_date = post.updated
                post_link = unicode(post.get_link('self'))

                registered = user.is_post_registered(post_link)
                if registered:
                    #log.msg('ignoring "%s"' % post_link)
                    # не показываем посты которые уже были показаны
                    continue

                post_link = yield user.register_post(post_link)

                parts = [
                    u'%s) %s, %s: ' % (post_link.hash, post.author, post.post_type)
                ]
                html_parts = [
                    u'<a href="%s">%s</a>) %s, %s: ' % (
                        post.get_link('alternate'),
                        post_link.hash,
                        post.author,
                        post.post_type
                    )
                ]
                title = post.title

                content_type, content = post.content

                if title:
                    parts[0] += title
                    html_parts[0] += title
                    if content:
                        parts.append(content)
                        html_parts.append(content)
                else:
                    if content:
                        parts[0] += content
                        html_parts[0] += content

                message = u'\n'.join(parts)

                html_message = u'<br/>'.join(html_parts)
                html_message = html_message.replace(u'&lt;', u'<')
                html_message = html_message.replace(u'&gt;', u'>')

                log.msg('Post %s: %s' % (post_link.hash.encode('utf-8'), html_message.encode('utf-8')))
                self.bot.send_html(user.jid, message, html_message)

            def cb_commited(result):
                print 'TRANSACTION COMMITED 2'
                return result
            store.flush().addCallback(cb_commited)

        for user in self.users.values():
            db.pool.transact(process_user_posts, user)
