# -*- coding: utf-8 -*-
import simplejson

from pdb import set_trace
from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.web.error import NoResource
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.web.http_headers import Headers
from twisted.python import log
from twisted.web import server, resource, client
from urllib import urlencode
from bot.models import User
from bot import messages
from bot import db


class WebRoot(resource.Resource):
    isLeaf = True
    def __init__(self, bot):
        self.bot = bot
        resource.Resource.__init__(self)


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
                    client_id = self.bot.client_id,
                ))
            )

            def cb(data, *args, **kwargs):
                data = simplejson.loads(data)
                access_token = unicode(data['access_token'])
                refresh_token = unicode(data['refresh_token'])

                user = [None]
                @inlineCallbacks
                def add_user(store):
                    user[0] = yield store.find(User, User.jid == unicode(jid))
                    user[0] = yield user[0].one()

                    user[0].auth_token = access_token
                    user[0].refresh_token = refresh_token

                    yield store.add(user[0])

                    self.bot.send_plain(jid, messages.END_REGISTRATION)
                    request.setHeader('Content-Type', 'text/html; charset=UTF-8')
                    request.write('<html>Спасибо за регистрацию, %s!</html>' % jid)
                    request.finish()

                db.pool.transact(add_user)



            def eb(data):
                request.setHeader('Content-Type', 'text/html; charset=UTF-8')
                if hasattr(data.value, 'status') and hasattr(data.value, 'response'):
                    message = 'ERROR from YaRu: %s, %s, %s' % (
                        data.value.status,
                        data.value.message,
                        data.value.response
                    )
                else:
                    message = 'ERROR: %s' % data.value.message
                request.write('<html>%s</html>' % message)
                request.finish()

            d.addCallback(cb)
            d.addErrback(eb)
            return server.NOT_DONE_YET
        return NoResource

