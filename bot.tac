"""
Jabber bot to serve http://wow.ya.ru service.
"""

import locale
import yaml

from bot.protocols import MessageProtocol
from twisted.application import service
from twisted.words.protocols.jabber.jid import JID
from wokkel import client
from wokkel.disco import DiscoHandler
from wokkel.generic import VersionHandler
from twisted.internet import task

# Configuration parameters

locale.setlocale(locale.LC_ALL, '')

config = yaml.load(open('config.yml'))

THIS_JID = JID(config['bot']['jid'])
HOST = config['bot'].get('host', None)
PORT = config['bot'].get('port', 5222)
OTHER_JID = JID(config['bot']['other_jid'])
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
task.LoopingCall(message_protocol.process_new_posts).start(
    config['bot']['polling_interval'],
    now = False
)

DiscoHandler().setHandlerParent(bot)
VersionHandler('yaru-bot', '0.1.0').setHandlerParent(bot)

