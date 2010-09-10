# -*- coding: utf-8 -*-
import simplejson

from . import db
from . import messages
from . import stats
from . models import User
from jinja2 import Template, Environment, PackageLoader
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.python import log
from twisted.web.error import NoResource
from twisted.web.http_headers import Headers
from twisted.web import server, resource, client
from urllib import urlencode


class BaseResource(resource.Resource):
    def __init__(self, bot = None, templates = None):
        resource.Resource.__init__(self)

        if templates is None:
            templates = Environment(loader = PackageLoader('bot'))
        self.templates = templates
        self.bot = bot


    def render_to_request(self, request, template_name, *args, **kwargs):
        tmpl = self.templates.get_template(template_name)
        html = tmpl.render(*args, **kwargs).encode('utf-8')

        request.setHeader('Content-Type', 'text/html; charset=UTF-8')
        request.write(html)



class Index(BaseResource):
    isLeaf = False

    def __init__(self, bot):
        BaseResource.__init__(self, bot)
        self.putChild('auth', Auth(bot, self.templates))
        self.putChild('ChangeLog', ChangeLog(self.templates))


    def getChild(self, name, request):
        if name == '':
            return self
        return resource.Resource.getChild(self, name, request)


    def render_GET(self, request):
        self.render_to_request(request, 'index.html')
        request.finish()
        return server.NOT_DONE_YET



class Auth(BaseResource):
    isLeaf = True


    def render_GET(self, request):
        if 'state' in request.args and 'code' in request.args:
            jid = request.args['state'][0]
            code = request.args['code'][0]

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
                    stats.STATS['new_users'] += 1

                    self.bot.send_plain(jid, messages.END_REGISTRATION)
                    self.render_to_request(request, 'auth-done.html', jid = jid)
                    request.finish()

                db.pool.transact(add_user).addErrback(
                    lambda ignore: request.finish()
                )



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
                self.render_to_request(request, 'error.html', message = message)
                request.finish()

            d.addCallback(cb)
            d.addErrback(eb)
            return server.NOT_DONE_YET

        self.render_to_request(request, '404.html')
        request.finish()
        return server.NOT_DONE_YET



class ChangeLog(BaseResource):
    isLeaf = True

    def render_GET(self, request):
        self.render_to_request(request, 'changelog.html')
        request.finish()
        return server.NOT_DONE_YET
