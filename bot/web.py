# -*- coding: utf-8 -*-
import simplejson

from pdb import set_trace
from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.web.error import NoResource
from twisted.web.http_headers import Headers
from twisted.python import log
from twisted.web import server, resource, client
from urllib import urlencode
from bot.models import User
from bot import messages
from bot import db


class WebRoot(resource.Resource):
    def __init__(self, bot):
        self.bot = bot
        resource.Resource.__init__(self)


    isLeaf = True
    def render_GET(self, request):
        if 'state' in request.args and 'code' in request.args:
            jid = request.args['state'][0]
            code = request.args['code'][0]

            agent = Agent(reactor)
            d = client.getPage(
                'https://oauth.yandex.ru/token',
                method = 'POST',
                headers = {
                    'User-Agent': 'YaRu Jabber bot: http://yaru.svetlyak.ru'
                },
                postdata = urlencode(dict(
                    code = code,
                    grant_type = 'authorization_code',
                    client_id = '911aec2bd1f543e194d68bd916f2190c',
                ))
            )
            @db.transaction
            def cb(store, data, *args, **kwargs):
                data = simplejson.loads(data)
                access_token = unicode(data['access_token'])
                refresh_token = unicode(data['refresh_token'])

                def _user_found(user):
                    user.auth_token = access_token
                    user.refresh_token = refresh_token
                    store.add(user).addCallback(_user_updated).addErrback(log.err)
                    #store.flush().addCallback(_user_updated).addErrback(log.err)

                def _user_updated(result):
                    self.bot.send_plain(jid, messages.END_REGISTRATION)
                    request.setHeader('Content-Type', 'text/html; charset=UTF-8')
                    request.write('<html>Спасибо за регистрацию, %s!</html>' % jid)
                    request.finish()

                store.find(User, User.jid == unicode(jid))\
                    .addCallback(lambda r: r.one().addCallback(_user_found).addErrback(log.err))\
                    .addErrback(log.err)


            def eb(data):
                request.setHeader('Content-Type', 'text/html; charset=UTF-8')
                message = 'ERROR from YaRu: %s, %s, %s' % (data.value.status, data.value.message, data.value.response)
                request.write('<html>%s</html>' % message)
                request.finish()

            d.addCallback(cb)
            d.addErrback(eb)
            return server.NOT_DONE_YET
        return NoResource

