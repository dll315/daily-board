# -*- coding: utf-8 -*-
"""
每日看板服务（零依赖，Python 3.8+ 标准库）

功能：
- 三栏看板：每日古诗（今日诗词 API）/ 每日科技简报（新闻 API + AI 助理）/ 每日提醒（自定义）
- 管理页（密码登录）：企业微信机器人配置、AI 助理配置、定时推送、各栏目推送预览
- 定时推送由本服务常驻执行

运行：python server.py   （或双击 start.bat）  访问：http://localhost:3000
"""
import hashlib
import hmac
import json
import os
import random
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')
DATA_DIR = os.path.join(BASE_DIR, 'data')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
REMINDERS_FILE = os.path.join(DATA_DIR, 'reminders.json')
PUSHLOG_FILE = os.path.join(DATA_DIR, 'pushlog.json')

PORT = int(os.environ.get('PORT', '3000'))
TOKEN_TTL_MS = 7 * 24 * 3600 * 1000

# ---- 新闻源（多源并发聚合，镜像取最先成功者） ----
SOURCE_60S = ('60s日报', [
    'https://60s.viki.moe/v2/60s',
    'https://60s-api.viki.moe/v2/60s',
    'https://60s.crazyxz.top/v2/60s',
    'https://60s-api.eu.org/v2/60s',
])
HOT_SOURCES = [
    ('微博热搜', ['https://60s.viki.moe/v2/weibo', 'https://60s-api.viki.moe/v2/weibo']),
    ('头条热榜', ['https://60s.viki.moe/v2/toutiao', 'https://60s-api.viki.moe/v2/toutiao']),
    ('抖音热点', ['https://60s.viki.moe/v2/douyin', 'https://60s-api.viki.moe/v2/douyin']),
]
BRIEFING_TTL = 1800  # 简报缓存有效期（秒），到期自动重新聚合
BRIEFING_MAX = 18    # 简报最大条数
AI_TIMEOUT = 180     # AI 生成简报超时（秒），推理模型可能较慢

# 科技类关键词：用于把科技新闻排在简报前列
TECH_KEYWORDS = [
    '科技', 'AI', '人工智能', '大模型', '芯片', '半导体', '算力', '互联网', '数码',
    '手机', '平板', '笔记本', '电脑', 'CPU', 'GPU', '软件', '硬件', 'App', 'APP',
    '应用', '操作系统', '鸿蒙', '安卓', 'iOS', '苹果', '华为', '小米', 'OPPO', 'vivo',
    '荣耀', '三星', '特斯拉', '比亚迪', '新能源', '电动车', '电动汽车', '自动驾驶',
    '智能驾驶', '电池', '充电', '机器人', '无人机', '卫星', '火箭', '航天', '太空',
    'NASA', '5G', '6G', '通信', '网络', '数据', '算法', '云计算', '云服务', '服务器',
    '电商', '直播', '短视频', '社交', '游戏', '电竞', '网信', '工信部', '专利', '研发',
    '智能', '数字', '量子', '区块链', '比特币', '网络安全', '黑客', '英特尔', '英伟达',
    'AMD', '高通', '台积电', '微软', '谷歌', 'OpenAI', '字节', '腾讯', '阿里', '百度',
    '京东', '拼多多', '网易', 'B站', '哔哩', '微博', '美团', '滴滴', '宁德', '支付系统',
]


def is_tech(s):
    low = s.lower()
    return any(k.lower() in low for k in TECH_KEYWORDS)


def filter_tech(items):
    return [s for s in items if is_tech(s)]

POEM_API = 'https://v1.jinrishici.com/all.json'

LOCAL_POEMS = [
    {'origin': '静夜思', 'author': '李白', 'dynasty': '唐',
     'lines': ['床前明月光，', '疑是地上霜。', '举头望明月，', '低头思故乡。']},
    {'origin': '春晓', 'author': '孟浩然', 'dynasty': '唐',
     'lines': ['春眠不觉晓，', '处处闻啼鸟。', '夜来风雨声，', '花落知多少。']},
    {'origin': '登鹳雀楼', 'author': '王之涣', 'dynasty': '唐',
     'lines': ['白日依山尽，', '黄河入海流。', '欲穷千里目，', '更上一层楼。']},
    {'origin': '相思', 'author': '王维', 'dynasty': '唐',
     'lines': ['红豆生南国，', '春来发几枝。', '愿君多采撷，', '此物最相思。']},
    {'origin': '江雪', 'author': '柳宗元', 'dynasty': '唐',
     'lines': ['千山鸟飞绝，', '万径人踪灭。', '孤舟蓑笠翁，', '独钓寒江雪。']},
    {'origin': '悯农', 'author': '李绅', 'dynasty': '唐',
     'lines': ['锄禾日当午，', '汗滴禾下土。', '谁知盘中餐，', '粒粒皆辛苦。']},
    {'origin': '清明', 'author': '杜牧', 'dynasty': '唐',
     'lines': ['清明时节雨纷纷，', '路上行人欲断魂。', '借问酒家何处有？', '牧童遥指杏花村。']},
    {'origin': '黄鹤楼送孟浩然之广陵', 'author': '李白', 'dynasty': '唐',
     'lines': ['故人西辞黄鹤楼，', '烟花三月下扬州。', '孤帆远影碧空尽，', '唯见长江天际流。']},
    {'origin': '早发白帝城', 'author': '李白', 'dynasty': '唐',
     'lines': ['朝辞白帝彩云间，', '千里江陵一日还。', '两岸猿声啼不住，', '轻舟已过万重山。']},
    {'origin': '枫桥夜泊', 'author': '张继', 'dynasty': '唐',
     'lines': ['月落乌啼霜满天，', '江枫渔火对愁眠。', '姑苏城外寒山寺，', '夜半钟声到客船。']},
    {'origin': '山行', 'author': '杜牧', 'dynasty': '唐',
     'lines': ['远上寒山石径斜，', '白云生处有人家。', '停车坐爱枫林晚，', '霜叶红于二月花。']},
    {'origin': '饮湖上初晴后雨', 'author': '苏轼', 'dynasty': '宋',
     'lines': ['水光潋滟晴方好，', '山色空蒙雨亦奇。', '欲把西湖比西子，', '淡妆浓抹总相宜。']},
]

DEFAULT_AI_PROMPT = (
    '你是科技简报编辑。请从下面的新闻列表中筛选出科技、互联网、AI、数码、航天等科技相关内容，'
    '整理成一份中文科技简报：第一行输出「【今日科技简报】X月X日」，然后列出 8~12 条要点，'
    '每条一行、以 - 开头，简明扼要突出重点，最后用一行「今日看点：…」做一句话总结。'
    '直接输出内容，不要任何解释。'
)


# ---------------------------------------------------------------- 存储工具
def read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pad(n):
    return '%02d' % n


def date_str(d=None):
    d = d or datetime.now()
    return '%d-%02d-%02d' % (d.year, d.month, d.day)


def time_str(d=None):
    d = d or datetime.now()
    return '%02d:%02d' % (d.hour, d.minute)


def sha256(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def load_config():
    salt = uuid.uuid4().hex[:16]
    default = {
        'secret': uuid.uuid4().hex,
        'auth': {'salt': salt, 'hash': sha256(salt + ':admin123')},
        'wechat': {'webhook': ''},
        'ai': {
            'enabled': False,
            'baseUrl': 'https://api.openai.com/v1',
            'apiKey': '',
            'model': 'gpt-4o-mini',
            'prompt': DEFAULT_AI_PROMPT,
        },
        'schedules': {
            'poem': {'enabled': False, 'time': '08:00', 'lastDate': ''},
            'briefing': {'enabled': False, 'time': '08:30', 'lastDate': ''},
            'reminders': {'enabled': False, 'time': '09:00', 'lastDate': ''},
        },
    }
    saved = read_json(CONFIG_FILE, {})
    cfg = {
        'secret': saved.get('secret') or default['secret'],
        'auth': {**default['auth'], **(saved.get('auth') or {})},
        'wechat': {**default['wechat'], **(saved.get('wechat') or {})},
        'ai': {**default['ai'], **(saved.get('ai') or {})},
        'schedules': {},
    }
    for key, val in default['schedules'].items():
        cfg['schedules'][key] = {**val, **((saved.get('schedules') or {}).get(key) or {})}
    return cfg


config = load_config()


def save_config():
    write_json(CONFIG_FILE, config)


# ---------------------------------------------------------------- 登录令牌
def make_token():
    exp = int(time.time() * 1000) + TOKEN_TTL_MS
    sig = hmac.new(config['secret'].encode(), ('admin:%d' % exp).encode(), hashlib.sha256).hexdigest()
    return '%d.%s' % (exp, sig)


def verify_token(token):
    try:
        exp_str, sig = str(token).split('.', 1)
        exp = int(exp_str)
        if exp < int(time.time() * 1000):
            return False
        expect = hmac.new(config['secret'].encode(), ('admin:%d' % exp).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expect)
    except Exception:
        return False


def is_admin(headers):
    m = re.match(r'^Bearer (.+)$', headers.get('Authorization') or '')
    return bool(m and verify_token(m.group(1)))


# ---------------------------------------------------------------- HTTP 客户端
def http_json(url, payload=None, timeout=12, headers=None, method=None):
    req_headers = {'User-Agent': 'Mozilla/5.0 DailyBoard/1.0'}
    if headers:
        req_headers.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req_headers['Content-Type'] = 'application/json'
    req = urlrequest.Request(url, data=data, headers=req_headers, method=method or ('POST' if data else 'GET'))
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode('utf-8', 'replace')
    try:
        return json.loads(body)
    except Exception:
        return body


# ---------------------------------------------------------------- 古诗
def get_poem(force=False):
    today = date_str()
    cache_file = os.path.join(CACHE_DIR, 'poem-%s.json' % today)
    if not force:
        cached = read_json(cache_file, None)
        if cached:
            return cached
    poem = None
    try:
        r = http_json(POEM_API, timeout=10)
        if isinstance(r, dict) and r.get('content'):
            poem = {
                'content': r['content'],
                'origin': r.get('origin') or '',
                'author': r.get('author') or '',
                'dynasty': '',
                'category': r.get('category') or '',
                'source': 'jinrishici',
            }
    except Exception as e:
        print('[古诗] 今日诗词 API 获取失败，使用本地诗库：', e)
    if not poem:
        p = random.choice(LOCAL_POEMS)
        poem = {
            'content': '\n'.join(p['lines']),
            'lines': p['lines'],
            'origin': p['origin'],
            'author': p['author'],
            'dynasty': p['dynasty'],
            'category': '',
            'source': 'local',
        }
    write_json(cache_file, poem)
    return poem


# ---------------------------------------------------------------- 科技简报
def _parse_60s(r):
    data = r.get('data') if isinstance(r, dict) else None
    news = (data or {}).get('news') if isinstance(data, dict) else None
    if not isinstance(news, list) or not news:
        raise RuntimeError('响应格式不符')
    return [str(x).strip() for x in news if str(x).strip()]


def _parse_hot(r):
    data = r.get('data') if isinstance(r, dict) else None
    if not isinstance(data, list) or not data:
        raise RuntimeError('响应格式不符')
    out = []
    for x in data:
        t = str(x.get('title') or '').strip().strip('#').strip() if isinstance(x, dict) else ''
        if t:
            out.append(t)
    if not out:
        raise RuntimeError('响应格式不符')
    return out


def _fetch_source(name, urls, parser):
    for url in urls:
        try:
            items = parser(http_json(url, timeout=8))
            if items:
                return {'name': name, 'items': items}
        except Exception:
            continue
    return None


def collect_news():
    """并发抓取全部新闻源，返回成功源列表 [{'name': 源名, 'items': [...]}]"""
    tasks = [(SOURCE_60S[0], SOURCE_60S[1], _parse_60s)] + \
            [(n, u, _parse_hot) for n, u in HOT_SOURCES]
    out = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        for fut in as_completed([ex.submit(_fetch_source, *t) for t in tasks]):
            r = fut.result()
            if r:
                out.append(r)
    return out


def merge_news(sources):
    """多源合并去重：科技类置顶，各热榜按名次轮询穿插。返回 [{'t': 文本, 's': 来源}]"""
    seen, merged = set(), []

    def key(s):
        return re.sub(r'[\s#＃!！?？。，,．.:：;；"\'「」『』【】（）()\[\]—\-]', '', s).lower()[:24]

    def add(text, src):
        k = key(text)
        if not k or k in seen:
            return
        seen.add(k)
        merged.append({'t': text, 's': src})

    s60 = next((x for x in sources if x['name'] == SOURCE_60S[0]), None)
    hots = [x for x in sources if x['name'] != SOURCE_60S[0]]
    s60_items = s60['items'] if s60 else []
    rr = []
    for i in range(30):
        for h in hots:
            if i < len(h['items']):
                rr.append((h['items'][i], h['name']))
    for t in filter_tech(s60_items):
        add(t, SOURCE_60S[0])
    for t, s in rr:
        if is_tech(t):
            add(t, s)
    for t in s60_items:
        add(t, SOURCE_60S[0])
    for t, s in rr:
        add(t, s)
    return merged


def build_news_result(sources, note_prefix=''):
    merged = merge_news(sources)
    items = merged[:BRIEFING_MAX]
    tech_count = sum(1 for x in items if is_tech(x['t']))
    src_names = '、'.join(sorted({x['s'] for x in merged}))
    if tech_count >= 5:
        note = ''
    elif tech_count:
        note = '今日科技类新闻较少（%d 条，已置顶），其余为各平台实时热点' % tech_count
    else:
        note = '今日未匹配到科技类新闻，已展示各平台实时热点'
    if note_prefix:
        note = note_prefix + ('；' + note if note else '')
    return {'source': 'news', 'date': date_str(), 'items': items, 'sources': src_names,
            'techCount': tech_count, 'note': note, 'updatedAt': time_str()}


def get_briefing(force=False, wait_ai=False):
    today = date_str()
    cache_file = os.path.join(CACHE_DIR, 'briefing-%s.json' % today)
    if not force:
        cached = read_json(cache_file, None)
        if cached and time.time() - cached.get('fetchedAt', 0) < BRIEFING_TTL:
            return cached
    sources = collect_news()
    if not sources:
        return {'source': 'none', 'date': today, 'markdown': '', 'updatedAt': time_str(),
                'note': '暂时无法获取新闻源，请检查网络后点击刷新重试'}

    def save(result):
        result['fetchedAt'] = time.time()
        write_json(cache_file, result)
        return result

    merged = merge_news(sources)
    ai_on = bool(config['ai'].get('enabled') and config['ai'].get('apiKey'))

    def gen_ai():
        try:
            lines = '\n'.join('【%s】%s' % (x['s'], x['t']) for x in merged[:45])
            prompt = '今天是%s。\n\n%s\n\n新闻列表：\n%s' % (
                today, config['ai'].get('prompt') or DEFAULT_AI_PROMPT, lines)
            markdown = call_ai(prompt, timeout=AI_TIMEOUT)
            save({'source': 'ai', 'date': today, 'markdown': markdown,
                  'newsCount': len(merged), 'updatedAt': time_str()})
            print('[简报] AI 简报已生成并缓存')
        except Exception as e:
            print('[简报] AI 生成失败：', e)
            save(build_news_result(sources, note_prefix='AI 生成失败，已回退为新闻列表'))

    if ai_on:
        if wait_ai:
            # 显式刷新 / 管理页预览 / 定时推送：等待 AI 完成
            gen_ai()
            return read_json(cache_file, None) or build_news_result(sources)
        # 页面浏览：立即返回聚合新闻版，AI 在后台生成，完成后自动替换缓存
        result = build_news_result(sources)
        pending = 'AI 简报正在后台生成（约需 15~90 秒），完成后自动替换，稍后点「刷新」可查看 AI 版'
        result['note'] = pending + ('；' + result['note'] if result['note'] else '')
        save(result)
        threading.Thread(target=gen_ai, daemon=True).start()
        return result
    return save(build_news_result(sources))


def call_ai(prompt, timeout=90):
    ai = config['ai']
    base = (ai['baseUrl'] or '').rstrip('/')
    if not base or not ai['apiKey']:
        raise RuntimeError('AI 助理未配置完整（API 地址 / API Key）')
    r = http_json(
        base + '/chat/completions',
        payload={'model': ai['model'], 'temperature': 0.5, 'stream': False,
                 'messages': [{'role': 'user', 'content': prompt}]},
        headers={'Authorization': 'Bearer ' + ai['apiKey']},
        timeout=timeout,
    )
    if not isinstance(r, dict):
        raise RuntimeError('AI 接口返回格式异常')
    if r.get('error'):
        msg = r['error']
        raise RuntimeError('AI 接口错误：%s' % (msg.get('message') if isinstance(msg, dict) else msg))
    choices = r.get('choices') or []
    content = (choices[0].get('message') or {}).get('content') if choices else None
    if not content:
        raise RuntimeError('AI 未返回内容：%s' % json.dumps(r, ensure_ascii=False)[:200])
    return content.strip()


# ---------------------------------------------------------------- 企业微信推送
def truncate_utf8(s, max_bytes=4000):
    out, used = [], 0
    for ch in s:
        b = len(ch.encode('utf-8'))
        if used + b > max_bytes:
            out.append('\n…（内容过长已截断）')
            break
        out.append(ch)
        used += b
    return ''.join(out)


def footer():
    return '\n> —— 来自「每日看板」 %s %s' % (date_str(), time_str())


def push_wechat(markdown):
    url = (config['wechat'].get('webhook') or '').strip()
    if not url:
        raise RuntimeError('尚未配置企业微信机器人 Webhook 地址，请先在管理页填写')
    r = http_json(url, payload={'msgtype': 'markdown',
                                'markdown': {'content': truncate_utf8(markdown)}},
                  timeout=15)
    if isinstance(r, dict) and r.get('errcode') != 0:
        raise RuntimeError('企业微信返回错误：%s %s' % (r.get('errcode'), r.get('errmsg')))
    return r


def poem_markdown(p):
    lines = p.get('lines') or (p['content'].split('\n'))
    quote = '\n'.join('> ' + l for l in lines)
    by = ' · '.join([x for x in [p.get('author'), p.get('dynasty')] if x])
    title = ('《%s》' % p['origin']) if p.get('origin') else ''
    return '## 📜 每日古诗\n\n%s\n\n**%s**　%s' % (quote, title, by) + footer()


def briefing_markdown(b):
    if b.get('source') == 'ai' and b.get('markdown'):
        return b['markdown'].strip() + footer()
    lines = []
    for i in (b.get('items') or []):
        if isinstance(i, dict):
            lines.append('- 【%s】%s' % (i.get('s', ''), i.get('t', '')))
        else:
            lines.append('- %s' % i)
    return '## 🤖 每日科技简报\n\n%s' % ('\n'.join(lines) or '今日暂无新闻数据') + footer()


def reminders_markdown():
    lst = read_json(REMINDERS_FILE, [])
    pending = [r for r in lst if not r.get('done')]
    if not pending:
        return '## ⏰ 每日提醒\n\n今日暂无待办提醒 🎉' + footer()
    body = '\n'.join('**%d.** %s' % (i + 1, r['text']) for i, r in enumerate(pending))
    return '## ⏰ 每日提醒\n\n%s' % body + footer()


def run_push(target, force=False):
    if target == 'test':
        return push_wechat('## ✅ 推送测试成功\n\n企业微信机器人连接正常！这是一条来自「每日看板」的测试消息。' + footer())
    if target == 'poem':
        return push_wechat(poem_markdown(get_poem(False)))
    if target == 'briefing':
        return push_wechat(briefing_markdown(get_briefing(force, wait_ai=True)))
    if target == 'reminders':
        return push_wechat(reminders_markdown())
    raise RuntimeError('未知的推送目标：%s' % target)


def add_log(target, ok, detail):
    logs = read_json(PUSHLOG_FILE, [])
    logs.insert(0, {'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'target': target, 'ok': ok, 'detail': detail})
    write_json(PUSHLOG_FILE, logs[:100])


# ---------------------------------------------------------------- 定时推送
def check_schedules():
    today = date_str()
    now = time_str()
    for key, s in config['schedules'].items():
        if not s.get('enabled') or not s.get('time') or s.get('lastDate') == today:
            continue
        if s['time'] == now:
            s['lastDate'] = today
            save_config()
            print('[定时推送] %s @ %s' % (key, now))
            try:
                run_push(key)
                add_log(key, True, '定时推送成功')
            except Exception as e:
                add_log(key, False, str(e))
                print('[定时推送失败]', key, e)


def scheduler_loop():
    while True:
        try:
            check_schedules()
        except Exception as e:
            print('[scheduler]', e)
        time.sleep(15)


# ---------------------------------------------------------------- HTTP 服务
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
        '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon'}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        pass

    # ---- 响应工具 ----
    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0 or length > 1024 * 1024:
            return {}
        raw = self.rfile.read(length).decode('utf-8', 'replace')
        try:
            return json.loads(raw)
        except Exception:
            return {}

    # ---- 路由 ----
    def do_GET(self):
        self.route('GET')

    def do_POST(self):
        self.route('POST')

    def route(self, method):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

            if path.startswith('/api/'):
                self.handle_api(method, path, query)
                return
            if method == 'GET':
                self.serve_static(path)
                return
            self.send_json(404, {'error': 'Not Found'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except RuntimeError as e:
            # 业务错误（未配置 webhook、AI 参数缺失、上游返回错误等）
            try:
                self.send_json(400, {'error': str(e)})
            except Exception:
                pass
        except Exception as e:
            try:
                self.send_json(500, {'error': str(e)})
            except Exception:
                pass

    # ---- 静态文件 ----
    def serve_static(self, path):
        if path == '/':
            path = '/index.html'
        file_path = os.path.normpath(os.path.join(PUBLIC_DIR, path.lstrip('/')))
        if not file_path.startswith(PUBLIC_DIR):
            self.send_json(403, {'error': 'Forbidden'})
            return
        if not os.path.isfile(file_path):
            self.send_response(404)
            body = b'Not Found'
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        ext = os.path.splitext(file_path)[1].lower()
        with open(file_path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', MIME.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- API ----
    def handle_api(self, method, path, query):
        refresh = query.get('refresh') == '1'

        if path == '/api/health' and method == 'GET':
            return self.send_json(200, {'ok': True, 'time': datetime.now().isoformat()})

        # 公开接口
        if path == '/api/poem' and method == 'GET':
            return self.send_json(200, get_poem(refresh))
        if path == '/api/briefing' and method == 'GET':
            # 手动刷新等待 AI 完成；普通浏览走缓存/后台生成，保证秒开
            return self.send_json(200, get_briefing(refresh, wait_ai=refresh))
        if path == '/api/reminders' and method == 'GET':
            return self.send_json(200, read_json(REMINDERS_FILE, []))
        if path == '/api/reminders' and method == 'POST':
            body = self.read_body()
            text = str(body.get('text') or '').strip()[:200]
            if not text:
                return self.send_json(400, {'error': '提醒内容不能为空'})
            lst = read_json(REMINDERS_FILE, [])
            item = {'id': uuid.uuid4().hex, 'text': text, 'done': False,
                    'createdAt': datetime.now().isoformat()}
            lst.append(item)
            write_json(REMINDERS_FILE, lst)
            return self.send_json(200, item)

        m = re.match(r'^/api/reminders/([0-9a-f]+)/(\w+)$', path)
        if m and method == 'POST':
            action = m.group(2)
            lst = read_json(REMINDERS_FILE, [])
            if action == 'toggle':
                for r in lst:
                    if r['id'] == m.group(1):
                        r['done'] = not r.get('done')
                        break
                else:
                    return self.send_json(404, {'error': '提醒不存在'})
            elif action == 'delete':
                lst = [r for r in lst if r['id'] != m.group(1)]
            else:
                return self.send_json(404, {'error': '未知操作'})
            write_json(REMINDERS_FILE, lst)
            return self.send_json(200, {'ok': True})

        # 登录
        if path == '/api/auth/login' and method == 'POST':
            body = self.read_body()
            password = str(body.get('password') or '')
            if sha256(config['auth']['salt'] + ':' + password) == config['auth']['hash']:
                return self.send_json(200, {'token': make_token()})
            return self.send_json(401, {'error': '密码错误'})
        if path == '/api/auth/check' and method == 'POST':
            ok = is_admin(self.headers)
            return self.send_json(200 if ok else 401, {'ok': ok})

        # 管理接口（需登录）
        if path.startswith('/api/admin/'):
            if not is_admin(self.headers):
                return self.send_json(401, {'error': '未登录或登录已过期'})

            if path == '/api/admin/config' and method == 'GET':
                return self.send_json(200, {'wechat': config['wechat'], 'ai': config['ai'],
                                            'schedules': config['schedules']})
            if path == '/api/admin/config' and method == 'POST':
                body = self.read_body()
                if isinstance(body.get('wechat'), dict):
                    config['wechat'].update(body['wechat'])
                if isinstance(body.get('ai'), dict):
                    config['ai'].update(body['ai'])
                if isinstance(body.get('schedules'), dict):
                    for key, s in config['schedules'].items():
                        ns = body['schedules'].get(key)
                        if not isinstance(ns, dict):
                            continue
                        if str(ns.get('time') or '') != s.get('time'):
                            s['lastDate'] = ''
                        s['enabled'] = bool(ns.get('enabled'))
                        if ns.get('time'):
                            s['time'] = str(ns['time'])
                save_config()
                return self.send_json(200, {'ok': True})
            if path == '/api/admin/ai/test' and method == 'POST':
                reply = call_ai('请原样回复四个字：连接成功', timeout=30)
                return self.send_json(200, {'ok': True, 'reply': reply})
            if path == '/api/admin/ai/preview' and method == 'POST':
                return self.send_json(200, get_briefing(True, wait_ai=True))
            if path == '/api/admin/push' and method == 'POST':
                body = self.read_body()
                target = str(body.get('target') or '')
                result = run_push(target, bool(body.get('force')))
                add_log(target, True, '手动推送成功')
                return self.send_json(200, {'ok': True, 'result': result})
            if path == '/api/admin/password' and method == 'POST':
                body = self.read_body()
                if sha256(config['auth']['salt'] + ':' + str(body.get('oldPassword') or '')) \
                        != config['auth']['hash']:
                    return self.send_json(400, {'error': '原密码不正确'})
                new_pwd = str(body.get('newPassword') or '')
                if len(new_pwd) < 6:
                    return self.send_json(400, {'error': '新密码至少 6 位'})
                salt = uuid.uuid4().hex[:16]
                config['auth'] = {'salt': salt, 'hash': sha256(salt + ':' + new_pwd)}
                save_config()
                return self.send_json(200, {'ok': True, 'token': make_token()})
            if path == '/api/admin/logs' and method == 'GET':
                return self.send_json(200, read_json(PUSHLOG_FILE, []))

        return self.send_json(404, {'error': '接口不存在'})


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    threading.Thread(target=scheduler_loop, daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    url = 'http://localhost:%d' % PORT
    print('=' * 50)
    print('  每日看板已启动：%s' % url)
    print('  管理页：右上角「设置」→ 默认密码 admin123')
    print('  数据目录：%s' % DATA_DIR)
    print('=' * 50)
    if os.environ.get('NO_OPEN') != '1' and os.name == 'nt':
        threading.Timer(1.0, lambda: os.system('start "" "%s"' % url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')


if __name__ == '__main__':
    main()
