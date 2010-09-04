"""
Jabber bot to serve http://wow.ya.ru service.
"""

import locale
import os
import yaml

from bot import db
from bot.protocols import MessageProtocol, PresenceProtocol
from bot.web import Index, Auth
from bot.scheduler import Scheduler
from pdb import set_trace
from twisted.application import service
from twisted.application.internet import TCPServer
from twisted.internet import task
from twisted.internet.defer import DebugInfo
from twisted.python import log, failure
from twisted.web import server
from twisted.words.protocols.jabber.jid import JID
from wokkel.disco import DiscoHandler
from wokkel.generic import VersionHandler
from wokkel import client

import twisted.manhole.telnet


# Configuration parameters

locale.setlocale(locale.LC_ALL, '')

config = yaml.load(open(os.environ.get('CONFIG', 'config.yml')))

db_started = db.init(config['database'])

THIS_JID = JID(config['bot']['jid'])
HOST = config['bot'].get('host', None)
PORT = config['bot'].get('port', 5222)
SECRET = config['bot']['pass']
LOG_TRAFFIC = True


# Set up the Twisted application

application = service.Application("YaRu Bot")

bot = client.XMPPClient(THIS_JID, SECRET, host = HOST, port = PORT)
bot.logTraffic = LOG_TRAFFIC
bot.setServiceParent(application)
bot.send('<presence/>') # Hello, OpenFire!

message_protocol = MessageProtocol(config)
message_protocol.setHandlerParent(bot)

presence_protocol = PresenceProtocol(config)
presence_protocol.setHandlerParent(bot)

DiscoHandler().setHandlerParent(bot)
VersionHandler('yaru-bot', '0.1.0').setHandlerParent(bot)

web_root = Index(message_protocol)

web_site = server.Site(web_root)
web_server = TCPServer(config['web']['port'], web_site)
web_server.setServiceParent(application)


def init_scheduler(ignore):
    scheduler = Scheduler(config.get('scheduler', {}), message_protocol)

    def process_new_posts():
        try:
            scheduler.process_new_posts()
        except Exception:
            DebugInfo().failResult = failure.Failure()

    if not config['bot'].get('disable_post_processing'):
        task.LoopingCall(process_new_posts).start(
            config['bot']['polling_interval'],
            now = False
        )

db_started.addCallback(init_scheduler)

# Add a manhole shell
debug_port = config['bot'].get('debug_port')

if debug_port:
    f = twisted.manhole.telnet.ShellFactory()
    f.username = config['bot']['debug_user']
    f.password = config['bot']['debug_pass']
    f.namespace['bot'] = message_protocol
    f.namespace['presence'] = presence_protocol
    manhole = TCPServer(debug_port, f)
    manhole.setServiceParent(application)

