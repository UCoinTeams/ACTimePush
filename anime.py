import json
from bisect import bisect_left
from colorsys import hsv_to_rgb, rgb_to_hsv
from datetime import date, datetime, timedelta
from io import BytesIO
from itertools import accumulate
from math import ceil, nan
from operator import truediv
from re import compile
import time

import jieba
import PIL.Image
import telebot
from more_itertools import chunked
from PIL.ImageColor import getrgb
from PIL.ImageDraw import Draw
from PIL.ImageEnhance import Brightness
from PIL.ImageFilter import GaussianBlur
from PIL.ImageFont import FreeTypeFont, truetype
from requests import get, post


def Fetch(start: datetime, end: datetime) -> list[dict]:
    # language=graphql
    query = """query ($page: Int = 1, $greater: Int, $lesser: Int) {
    Page(page: $page) {
        pageInfo {
            hasNextPage
            total
        }
        airingSchedules(airingAt_greater: $greater, airingAt_lesser: $lesser, sort: [TIME, EPISODE]) {
            episode
            airingAt
            media {
                id
                title {
                    native
                    romaji
                }
                coverImage {
                    extraLarge
                    color
                }
                episodes
                type
                countryOfOrigin
                format
                source
                duration
                genres
                studios {
                    nodes {
                        name
                        isAnimationStudio
                    }
                }
                description
            }
        }
    }
}"""
    out = []
    for page in range(100):
        r = post('https://graphql.anilist.co', json={'query': query, 'variables': {'page': page, 'greater': start.timestamp() - 1, 'lesser': end.timestamp()}}).json()['data']['Page']
        out += r['airingSchedules']
        if not r['pageInfo']['hasNextPage']: break

    out = [s for s in out if s['media']['countryOfOrigin'] == 'JP' and s['media']['type'] == 'ANIME' and s['media']['format'] in ['TV', 'MOVIE', 'TV_SHORT', 'ONA'] and 'Hentai' not in s['media']['genres']]

    # Deduplicate
    # ----------------------------------------
    index = {}
    i = 0
    while i < len(out):
        q = out[i]['media']['id'], out[i]['airingAt']
        if q in index:
            out[index[q]]['episodeUntil'] = out.pop(i)['episode']
        else:
            index[q] = i
            i += 1

    for l in range(len(out)):
        out[l]['media']['score'] = 0
        out[l]['media']['no_space'] = False
        out[l]['bgm_id'] = None
        try:
            r = get(f'https://api.bgm.tv/search/subject/{out[l]["media"]["title"]["native"]}', 
            params = {"type": 2, "responseGroup": "large", "start": 0, "max_results": 1}).json()['list'][0]
        except:
            continue
        out[l]['media']['no_space'] = True
        out[l]['bgm_id'] = r['id']
        out[l]['media']['title']['native'] = r['name_cn'] or out[l]['media']['title']['native']
        out[l]['media']['description'] = ' '.join(jieba.cut(r['summary'])) or out[l]['media']['description']
        out[l]['media']['score'] = r['rating']['score'] if r.get('rating') else 0

    return out


def Wrap(text: str, width: float, font: FreeTypeFont, line=-1, no_space=False) -> list[str]:
    space = font.getlength(' ')
    dots = font.getlength('[...]')
    words = text.split()
    lens = tuple(accumulate(map(space.__add__, map(font.getlength, words))))  # Widths of words, each plus a space
    out = []
    w = width + space
    while line and words:
        i = bisect_left(lens, w)
        if line == 1:
            for j in reversed(range(i)):
                dots -= lens[j]
                if dots > 0:
                    words[j] = ''
                else:
                    words[j] = '[...]'
                    break
        if no_space:
            out.append(''.join(words[:i]))
        else:
            out.append(' '.join(words[:i]))
        w = width + lens[i - 1] + space  # Ignore space at line end
        words = words[i:]
        lens = lens[i:]
        line -= 1
    return out


def Card(info: list[dict]) -> list[bytes]:
    re0 = compile(r'Season (\d+)')  # E.g., Season 2 -> 2
    re1 = compile(r'<.*?>')  # E.g., <br>, <i>
    re2 = compile(r'\(Source: .*?\)')  # Usually at end
    re3 = compile(r'Note: .*')  # Usually at end

    fontM = truetype('font/iosevka-bold.ttf', 72)
    fontS = truetype('font/NotoSansSymbols2-Regular.ttf', 40)
    # fontJ = truetype('font/sarasa-ui-j-regular.ttf', 48)
    # font1 = truetype('font/OpenSans-VariableFont_wdth,wght.ttf', 24)
    font1 = truetype('font/NotoSansSC-Medium.otf', 24)
    font2 = font1.font_variant(size=36)
    font3 = font1.font_variant(size=48)
    # font1.set_variation_by_name('Condensed Bold')
    # font2.set_variation_by_name('Condensed Bold')
    # font3.set_variation_by_name('Condensed Bold')

    formats = {'TV_SHORT': 'TV Short', 'MOVIE': 'Movie'}
    sources = {'ORIGINAL': '原创', 'LIGHT_NOVEL': '轻小说改编', 'VISUAL_NOVEL': '视觉小说改编', 'VIDEO_GAME': '游戏改编', 'MANGA': '漫画改编', 'NOVEL': '小说改编', 'OTHER': '其他'}

    out = []
    for data in info:
        image = PIL.Image.new('RGB', (1000, 650), '#222526')
        draw = Draw(image)
        xl = 490
        width = 500
        color = getrgb(data['media']['coverImage']['color'] or '#73B9DF')

        # Thumbnail
        # ----------------------------------------
        with PIL.Image.open(BytesIO(get(data['media']['coverImage']['extraLarge']).content)) as thumb:
            size = (460, 650)  # Thumbnail size
            r = min(map(truediv, thumb.size, size))
            w = r * size[0]
            h = r * size[1]
            l = max(0, (thumb.size[0] - w) / 2)
            t = max(0, (thumb.size[1] - h) / 2)
            r = min(thumb.size[0], (thumb.size[0] + w) / 2)
            b = min(thumb.size[1], (thumb.size[1] + h) / 2)
            image.paste(thumb.resize(size, 1, (l, t, r, b), 2))  # Lanczos

            size = (540, 650)  # TODO: Don't hardcode
            r = 0.5 * min(map(truediv, thumb.size, size))
            w = r * size[0]
            h = r * size[1]
            l = max(0, (thumb.size[0] - w) / 2)
            t = max(0, (thumb.size[1] - h) / 2)
            r = min(thumb.size[0], (thumb.size[0] + w) / 2)
            b = min(thumb.size[1], (thumb.size[1] + h) / 2)
            image.paste(Brightness(thumb.resize(size, 1, (l, t, r, b), 2)).enhance(0.25).filter(GaussianBlur(9)), (460, 0))

        # Episode
        # ----------------------------------------
        yt = 30
        margin = 14
        episode = "{} {}{} / {} 的播出时间".format(
            (data['episode'] == data['media']['episodes'] or data.get('episodeUntil', nan) == data['media']['episodes']) and 'Final ep' or 'Ep',
            data['episode'],
            'episodeUntil' in data and f"-{data['episodeUntil']}" or '',
            data['media']['episodes'] or '?',
            # 'episodeUntil' in data and 'are' or 'is',
        )
        _, t, _, b = font1.getbbox('A')
        yt += b - t
        draw.text((xl, yt), episode, 'darkgray', font1, 'ls')
        yt += margin

        # Airing at
        # ----------------------------------------
        t = datetime.fromtimestamp(data['airingAt'])
        hh = f"{t.hour:02}"
        mm = f"{t.minute:02}"
        tmr = date.today() < t.date() and '+' or ''
        l, t, r, b = fontM.getbbox('0')
        yt += b - t
        h, s, v = rgb_to_hsv(*color)
        rgb = tuple(map(round, hsv_to_rgb(h, s * 0.4, v)))
        draw.text((xl - 3, yt), hh, color, fontM, 'ls')
        draw.text((xl - 3 + 2 * (r - l), yt), mm, rgb, fontM, 'ls')
        draw.text((xl - 3 + 4 * (r - l), yt), tmr, 'white', fontM, 'ls')
        yt += margin

        # Format and source
        # ----------------------------------------
        format = formats.get(data['media']['format'], data['media']['format'])
        source = sources.get(data['media']['source'], data['media']['source'].replace('_', ' ').title())
        duration = data['media']['duration'] and f" ({data['media']['duration']} min.)" or ''
        _, t, _, b = font1.getbbox('A')
        yt += b - t
        draw.text((xl, yt), f"{format}{duration} | {source}", 'white', font1, 'ls')
        yt += margin * 1.5

        # Score
        # ----------------------------------------
        if score := data['media']['score']:
            draw.text((865, 60), '\u2730', score >= 6 and 'gold' or score >= 5 and 'silver' or 'Sienna', fontS, 'ls')
            draw.text((910, 60), f"{data['media']['score']}", 'white', font2, 'ls')

        # Studio
        # ----------------------------------------
        yb = 550
        margin = 16
        studio = [studio['name'] for studio in data['media']['studios']['nodes'] if studio['isAnimationStudio']]
        _, t, _, b = font2.getbbox('A')
        spacing = 12
        yb -= (len(studio) - 1) * (b - t + spacing)
        draw.multiline_text((xl, yb), '\n'.join(studio), color, font2, 'ls', spacing - t)
        yb -= (b - t) + margin

        # Title
        # ----------------------------------------
        _title = data['media']['title']['native'] 
        native = re0.sub(r'\1', (_title if len(_title) < 9 else _title[:9] + " ...") or '').replace('’', "'")
        romaji = re0.sub(r'\1', data['media']['title']['romaji'] or '').replace('’', "'")
        if not native or native.casefold() == romaji.casefold():
            romaji = Wrap(romaji, width, font3)
            _, t, _, b = font3.getbbox('A')
            spacing = 14
            yb -= (len(romaji) - 1) * (b - t + spacing)
            draw.multiline_text((xl, yb), '\n'.join(romaji), 'white', font3, 'ls', spacing - t)
            yb -= (b - t) + margin * 1.5
        else:
            romaji = Wrap(romaji, width, font1)
            _, t, _, b = font1.getbbox('A')
            spacing = 10
            yb -= (len(romaji) - 1) * (b - t + spacing)
            draw.multiline_text((xl, yb), '\n'.join(romaji), 'white', font1, 'ls', spacing - t)
            yb -= (b - t) + margin
            native = Wrap(native, width, font3)
            _, t, _, b = font3.getbbox('A')
            spacing = 14
            yb -= (len(native) - 1) * (b - t + spacing)
            draw.multiline_text((xl, yb), '\n'.join(native), 'white', font3, 'ls', spacing - t)
            yb -= (b - t) + margin * 1.5

        # Description
        # ----------------------------------------
        desc = re3.sub('', re2.sub('', re1.sub('', data['media']['description'].replace('’', "'"))))
        _, t, _, b = font1.getbbox('A')
        spacing = 10
        yt += b - t
        desc = Wrap(desc, width, font1, ceil((yb - yt + spacing) / (b - t + spacing)), no_space=data['media']['no_space'])
        draw.multiline_text((xl, yt), '\n'.join(desc), 'gray', font1, 'ls', spacing - t)

        # Genre
        # ----------------------------------------
        y = 610
        border = 7
        xr = xl + width
        h, s, v = rgb_to_hsv(*color)
        rgb = tuple(map(round, hsv_to_rgb(h, s, v * 0.6)))
        for genre in data['media']['genres']:
            l, t, r, b = draw.textbbox((xl, y), genre, font1, 'ls')
            if r + 2 * border > xr: break  # Exceeding tags are dropped
            draw.rectangle((l, y - border, r + 2 * border, y + border), rgb)
            draw.text((l + border, y), genre, 'white', font1, 'ls')
            xl += r - l + border * 4  # Move right

        # Export
        # ----------------------------------------
        file = BytesIO()
        image.save(file, 'PNG')  # .tobytes() is not for this
        out.append([file.getvalue(), [data['bgm_id'], data['media']['title']['native']]])

    return out


def Task() -> None:
    send_id = 0
    start = datetime.now()
    start = start.replace(hour=17, minute=0, second=0, microsecond=0)
    cards = Card(Fetch(start, start + timedelta(1)))
    total = ceil(len(cards) / 10)
    isoformat = start.date().isoformat()
    bot = telebot.TeleBot('token') # set your token here
    msg_list = []
    for i, chunk in enumerate(chunked(cards, 10)):
        media = list(map(lambda p: telebot.types.InputMediaPhoto(p[0]), chunk))
        media[0].caption = f"`今日放送番剧\n{i + 1}/{total} {isoformat}`\n"
        for d in chunk:
            media[0].caption += f"\n  - [{d[1][1]}](https://t.me/BangumiBot?start={d[1][0]})"
        media[0].parse_mode = 'markdown'
        msg = bot.send_media_group(send_id, media)
        msg_list.append(msg[0].message_id)
        if len(cards) > 10: time.sleep(60)
    for id in msg_list:
        bot.pin_chat_message(send_id, id, disable_notification=True)
    f = open("./message_id", "r+")
    old_msg_list = json.loads(f.read())
    f.seek(0)
    f.truncate()
    f.write(json.dumps(msg_list))
    f.close()
    for oid in old_msg_list:
        bot.unpin_chat_message(send_id, oid)

if __name__ == '__main__':
    Task()
