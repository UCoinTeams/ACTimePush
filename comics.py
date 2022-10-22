from bisect import bisect_left
from colorsys import hsv_to_rgb, rgb_to_hsv
from datetime import datetime
from io import BytesIO
from itertools import accumulate
from math import ceil
from operator import truediv
from re import compile

import jieba
import PIL.Image
import telebot
from more_itertools import chunked
from PIL.ImageDraw import Draw
from PIL.ImageEnhance import Brightness
from PIL.ImageFilter import GaussianBlur
from PIL.ImageFont import FreeTypeFont, truetype
from requests import get


def Fetch() -> list[dict]:
    """获取排行榜数据"""
    r = get('https://m.dmzj.com/rank/2-0-0-0.json')
    out = []
    if r.status_code == 200:
        out = r.json()
    for l in range(len(out)):
        r = get(f'http://api.dmzj.com/dynamic/comicinfo/{out[l]["id"]}.json').json()['data']['info']
        out[l]['name'] = ' '.join(jieba.cut(r['title']))
        out[l]['name_ja'] = r['subtitle']
        out[l]['description'] = ' '.join(jieba.cut(r['description']))
        out[l]['last_update_chapter_name'] = r['last_update_chapter_name']
        out[l]['types'] = r['types'].split('/')
        out[l]['authors'] = r['authors'].split('/')
        out[l]['cover'] = r['cover']
        out[l]['color'] = Color(PIL.Image.open(BytesIO(get(out[l]['cover']).content))) or (34, 37, 38)
        out[l]['ranking'] = l + 1
    return out

def Color(image):
    """要提取的主要颜色"""
    try:
        num_colors = 20 
        small_image = image.resize((80, 80))
        result = small_image.convert('P', palette=PIL.Image.Palette.ADAPTIVE, colors=num_colors)
        result = result.convert('RGB')
        main_colors = result.getcolors()
        main_color = sorted(main_colors, key=lambda x: x[0], reverse=True)[0][1]
        if main_color[0] < 120:
            main_color = (150, main_color[1], main_color[2])
        if main_color[1] > 160:
            main_color = (main_color[0], 150, main_color[2])
    except:
        return None
    return main_color

def Wrap(text: str, width: float, font: FreeTypeFont, line=-1) -> list[str]:
    space = font.getlength(' ')
    dots = font.getlength('...')
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
                    words[j] = '...'
                    break
        out.append(''.join(words[:i]))
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

    fontM = truetype('font/NotoSansSC-Medium.otf', 72)
    # fontJ = truetype('font/sarasa-ui-j-regular.ttf', 48)
    # font1 = truetype('font/OpenSans-VariableFont_wdth,wght.ttf', 24)
    font1 = truetype('font/NotoSansSC-Medium.otf', 24)
    font2 = font1.font_variant(size=36)
    font3 = font1.font_variant(size=48)
    # font1.set_variation_by_name('Condensed Bold')
    # font2.set_variation_by_name('Condensed Bold')
    # font3.set_variation_by_name('Condensed Bold')

    out = []
    for data in info:
        image = PIL.Image.new('RGB', (1000, 650), '#222526')
        draw = Draw(image)
        xl = 490
        width = 500
        color = data['color']

        # Thumbnail
        # ----------------------------------------
        with PIL.Image.open(BytesIO(get(data['cover']).content)) as thumb:
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

        # Last Update Name
        # ----------------------------------------
        yt = 30
        margin = 14
        last_update = f"最后一次更新 {data['last_update_chapter_name']}"

        _, t, _, b = font1.getbbox('A')
        yt += b - t
        draw.text((xl, yt), last_update, 'darkgray', font1, 'ls')
        yt += margin

        # Ranking
        # ----------------------------------------
        l, t, r, b = fontM.getbbox('0')
        yt += b - t
        h, s, v = rgb_to_hsv(*color)
        rgb = tuple(map(round, hsv_to_rgb(h, s * 0.4, v)))
        draw.text((xl - 3, yt), '第 ', rgb, fontM, 'ls')
        if data['ranking'] < 10:
            draw.text((xl - 3 + 2.3 * (r - l), yt), str(data['ranking']), color, fontM, 'ls')
            draw.text((xl - 3 + 3.5 * (r - l), yt), ' 位', rgb, fontM, 'ls')
        else:
            draw.text((xl - 3 + 2 * (r - l), yt), str(data['ranking']), color, fontM, 'ls')
            draw.text((xl - 3 + 4 * (r - l), yt), ' 位', rgb, fontM, 'ls')
        yt += margin

        # Format and source
        # ----------------------------------------
        _, t, _, b = font1.getbbox('A')
        yt += b - t
        draw.text((xl, yt), f"当前时间排名 {datetime.now().strftime('%Y/%m/%d %H:%M')}", 'white', font1, 'ls')
        yt += margin * 1.5

        # Author
        # ----------------------------------------
        yb = 550
        margin = 16
        authors = data['authors']
        _, t, _, b = font2.getbbox('A')
        spacing = 12
        yb -= (len(authors) - 1) * (b - t + spacing)
        draw.multiline_text((xl, yb), ' '.join(authors), color, font2, 'ls', spacing - t)
        yb -= (b - t) + margin

        # Title
        # ----------------------------------------
        title = re0.sub(r'\1', data['name'] or '')
        _title_ja = data['name_ja']
        title_ja = re0.sub(r'\1', (_title_ja if len(_title_ja) < 30 else _title_ja[:30] + " ...") or '')
        if not title_ja:
            title = Wrap(title, width, font3)
            _, t, _, b = font3.getbbox('A')
            spacing = 14
            yb -= (len(title) - 1) * (b - t + spacing)
            draw.multiline_text((xl, yb), '\n'.join(title), 'white', font3, 'ls', spacing - t)
            yb -= (b - t) + margin * 1.5
        else:
            title_ja = Wrap(title_ja, width, font1)
            _, t, _, b = font1.getbbox('A')
            spacing = 10
            yb -= (len(title_ja) - 1) * (b - t + spacing)
            draw.multiline_text((xl, yb), '\n'.join(title_ja), 'white', font1, 'ls', spacing - t)
            yb -= (b - t) + margin
            title = Wrap(title, width, font3)
            _, t, _, b = font3.getbbox('A')
            spacing = 14
            yb -= (len(title) - 1) * (b - t + spacing)
            draw.multiline_text((xl, yb), '\n'.join(title), 'white', font3, 'ls', spacing - t)
            yb -= (b - t) + margin * 1.5

        # Description
        # ----------------------------------------
        desc = re3.sub('', re2.sub('', re1.sub('', data['description'])))
        _, t, _, b = font1.getbbox('A')
        spacing = 10
        yt += b - t
        desc = Wrap(desc, width, font1, ceil((yb - yt + spacing) / (b - t + spacing)))
        draw.multiline_text((xl, yt), '\n'.join(desc), 'gray', font1, 'ls', spacing - t)

        # Genre
        # ----------------------------------------
        y = 610
        border = 7
        xr = xl + width
        h, s, v = rgb_to_hsv(*color)
        rgb = tuple(map(round, hsv_to_rgb(h, s, v * 0.6)))
        for genre in data['types']:
            l, t, r, b = draw.textbbox((xl, y), genre, font1, 'ls')
            if r + 2 * border > xr: break  # Exceeding tags are dropped
            draw.rectangle((l, y - border, r + 2 * border, y + border), rgb)
            draw.text((l + border, y), genre, 'white', font1, 'ls')
            xl += r - l + border * 4  # Move right

        # Export
        # ----------------------------------------
        file = BytesIO()
        image.save(file, 'PNG')  # .tobytes() is not for this
        out.append(file.getvalue())

    return out

def Task() -> None:
    send_id = 0
    start = datetime.now()
    start = start.replace(hour=17, minute=0, second=0, microsecond=0)
    cards = Card(Fetch())
    total = ceil(len(cards) / 10)
    isoformat = start.date().isoformat()
    bot = telebot.TeleBot('token') # set your token here
    for i, chunk in enumerate(chunked(cards, 10)):
        media = list(map(telebot.types.InputMediaPhoto, chunk))
        media[0].caption = f"`动漫之家漫画订阅排行\n{i + 1}/{total} {isoformat} (UTC+9)`"
        media[0].parse_mode = 'markdown'
        bot.send_media_group(send_id, media)

if __name__ == '__main__':
    Task()
