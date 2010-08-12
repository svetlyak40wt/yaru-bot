# -*- coding: utf-8 -*-
from __future__ import with_statement

import datetime
import os.path
import pickle
import re

from bot.api import YaRuAPI
from hashlib import md5
from pdb import set_trace
from twisted.python import log
from twisted.words.xish import domish
from wokkel import xmppim


CHATSTATE_NS = 'http://jabber.org/protocol/chatstates'
HASH_LENGTH = 2
POST_HISTORY_LENGTH = 100

class MessageProtocol(xmppim.MessageProtocol):
    def __init__(self, cfg):
        super(MessageProtocol, self).__init__()
        self.jid = cfg['bot']['jid']
        self.other_jid = cfg['bot']['other_jid']
        self.cfg = cfg
        self._datafile = os.path.expanduser('~/.yaru-bot')
        self.posts = {} # map для хранения последних постов из френдленты
        self.dt_to_post = [] # сортированный по времени список постов

        self.load_state()



    def load_state(self):
        if os.path.exists(self._datafile):
            with open(self._datafile) as file:
                self.posts, self.dt_to_post = pickle.load(file)


    def save_state(self):
        with open(self._datafile, 'w') as file:
            pickle.dump(
                (self.posts, self.dt_to_post),
                file
            )


    def onMessage(self, msg):
        if msg['type'] == 'chat' and hasattr(msg, 'body') and msg.body:
            command = unicode(msg.body)

            if command == 'get':
                self.process_new_posts()

            if command == 'len':
                self.send_plain(self.other_jid, 
                    'len == %s' % len(self.parent._packetQueue))

            match = re.match(r'#(?P<hash>[a-z0-9]{2}) (?P<text>.*)', command)
            if match is not None:
                hash, message = match.groups()
                if hash in self.posts:
                    post = self.posts[hash]
                    post.reply(message)


    def process_new_posts(self):
        log.msg('Retriving posts from yaru.')

        api = YaRuAPI(**self.cfg['api'])
        for post in api.get_friend_feed():
            post_date = post.updated
            post_link = post.get_link('self')

            post_hash = md5(post_link).hexdigest()[:HASH_LENGTH]
            #log.msg('Post %s' % post_hash)

            if post_hash in self.posts:
                #log.msg('ignoring "%s"' % post_hash)
                # не показываем посты которые уже были показаны
                continue

            self.posts[post_hash] = post
            self.dt_to_post.append((post_date, post_hash))

            to_remove = self.dt_to_post[:-POST_HISTORY_LENGTH]
            self.dt_to_post = self.dt_to_post[-POST_HISTORY_LENGTH:]

            for dt, hash in to_remove:
                del self.posts[hash]

            self.save_state()


            parts = [
                u'%s) %s, %s: ' % (post_hash, post.author, post.post_type)
            ]
            try:
                html_parts = [
                    u'<a href="%s">%s</a>) %s, %s: ' % (
                        post.get_link('alternate'),
                        post_hash,
                        post.author,
                        post.post_type
                    )
                ]
            except:
                set_trace()
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

            log.msg('Post %s: %s' % (post_hash, html_message.encode('utf-8')))
            self.send_html(self.other_jid, message, html_message)



    def create_message(self):
        msg = domish.Element((None, 'message'))
        import time
        msg['id'] = str(time.time())
        msg.addElement((CHATSTATE_NS, 'active'))
        return msg


    def send_plain(self, jid, content):
        msg = self.create_message()
        msg['to'] = jid
        msg['from'] = self.jid
        msg['type'] = 'chat'
        msg.addElement('body', content = content)

        self.send(msg)


    def send_html(self, jid, body, html):
        msg = self.create_message()
        msg['to'] = jid
        msg['from'] = self.jid
        msg['type'] = 'chat'
        html = u'<html xmlns="http://jabber.org/protocol/xhtml-im"><body xmlns="http://www.w3.org/1999/xhtml">' + unicode(html) + u'</body></html>'
        msg.addRawXml(u'<body>' + unicode(body) + u'</body>')
        msg.addRawXml(unicode(html))

        self.send(msg)

