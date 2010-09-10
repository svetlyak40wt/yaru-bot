# -*- coding: utf-8 -*-
NEW_USER_WELCOME = u"""Привет, я Джинн Ярушки.

Я помогу тебе быстро узнавать о постах твоих друзей, и мгновенно комментировать их, даже не открывая браузер.
Для начала, дай мне доступ к своей Ярушечке.

Для этого, пройди по URL:
https://oauth.yandex.ru/authorize?client_id=%s&response_type=code&state=%s

Если будут затруднения, напиши мне "помощь" или "help".
"""

OLD_USER_WELCOME = u"""Добро пожаловать, хозяин.

Если захочешь освежить память, напиши мне "помощь" или "help".
"""

END_REGISTRATION = u"""Поздравляю, регистрация окончена!"""

HELP = u"""Я Джинн Ярушки, у тебя есть три желания...
...да ладно, шучу, шучу. Вот список команд, которые я понимаю:

[help|помощь|справка] — вывести эту подсказку.
[#<id>|№<id>] <текст комментария> — прокомментировать сообщение во френдленте. <хэш>, это идентификатор сообщения.
[post|пост] <текст заголовка>. <текст поста> — Если ввести одно предложение, то будет создан пост без заголовка.
[link|ссылка] <url> - <название> - <описание> — Запостить ссылку. Название и описание необязательны.

Если тебе надоели мои уведомления, открой страницу https://oauth.yandex.ru/list_tokens
и нажми кнопку «Запретить» напротив Jabber Bot.
"""

REQUIRE_AUTH_TOKEN = u"""Сначала, дай мне доступ к своей Ярушечке.

Для этого, пройди по URL:
https://oauth.yandex.ru/authorize?client_id=%s&response_type=code&state=%s
"""

REQUIRE_BE_ADMIN = u"""Эта команда доступна только администраторам сервиса."""

