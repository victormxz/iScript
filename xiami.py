#!/usr/bin/env python2
# vim: set fileencoding=utf8

import re
import sys
from getpass import getpass
import os
import random
import time
import json
import argparse
import requests
import urllib
import select
from mutagen.id3 import ID3,TRCK,TIT2,TALB,TPE1,APIC,TDRC,COMM,TPOS,USLT
from HTMLParser import HTMLParser

url_song = "http://www.xiami.com/song/%s"
url_album = "http://www.xiami.com/album/%s"
url_collect = "http://www.xiami.com/collect/%s"
url_artist_albums = "http://www.xiami.com/artist/album/id/%s/page/%s"
url_artist_top_song = "http://www.xiami.com/artist/top/id/%s"
url_lib_songs = "http://www.xiami.com/space/lib-song/u/%s/page/%s"
url_radio_my = "http://www.xiami.com/radio/xml/type/4/id/%s"  # 电台来源:来源于"收藏的歌曲","收藏的专辑","喜欢的艺人","我收藏的精选集"
url_radio_c = "http://www.xiami.com/radio/xml/type/8/id/%s"  # 虾米猜, 基于你的虾米试听行为所建立的个性电台

############################################################
# wget exit status
wget_es = {
    0:"No problems occurred.",
    2:"User interference.",
    1<<8:"Generic error code.",
    2<<8:"Parse error - for instance, when parsing command-line ' \
        'optio.wgetrc or .netrc...",
    3<<8:"File I/O error.",
    4<<8:"Network failure.",
    5<<8:"SSL verification failure.",
    6<<8:"Username/password authentication failure.",
    7<<8:"Protocol errors.",
    8<<8:"Server issued an error response."
}
############################################################

parser = HTMLParser()
s = '\x1b[%d;%dm%s\x1b[0m'       # terminual color template

cookie_file = os.path.join(os.path.expanduser('~'), '.Xiami.cookies')

headers = {
    "Accept":"text/html,application/xhtml+xml,application/xml; " \
        "q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding":"text/html",
    "Accept-Language":"en-US,en;q=0.8,zh-CN;q=0.6,zh;q=0.4,zh-TW;q=0.2",
    "Content-Type":"application/x-www-form-urlencoded",
    "Referer":"http://www.xiami.com/",
    "User-Agent":"Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 "\
        "(KHTML, like Gecko) Chrome/32.0.1700.77 Safari/537.36"
}

ss = requests.session()
ss.headers.update(headers)

############################################################
# Regular Expression Templates
re_disc_description = r'disc (\d+) \[(.+?)\]'
############################################################

def decry(row, encryed_url):
    url = encryed_url
    urllen = len(url)
    rows = int(row)

    cols_base = urllen / rows  # basic column count
    rows_ex = urllen % rows    # count of rows that have 1 more column

    matrix = []
    for r in xrange(rows):
        length = cols_base + 1 if r < rows_ex else cols_base
        matrix.append(url[:length])
        url = url[length:]

    url = ''
    for i in xrange(urllen):
        url += matrix[i % rows][i / rows]

    return urllib.unquote(url).replace('^', '0')

def modificate_text(text):
    text = parser.unescape(text)
    text = re.sub(r'//*', '-', text)
    text = text.replace('/', '-')
    text = text.replace('\\', '-')
    text = re.sub(r'\s\s+', ' ', text)
    text = text.strip()
    return text

def modificate_file_name_for_wget(file_name):
    file_name = re.sub(r'\s*:\s*', u' - ', file_name)    # for FAT file system
    file_name = file_name.replace('?', '')      # for FAT file system
    file_name = file_name.replace('"', '\'')    # for FAT file system
    file_name = file_name.replace('$', '\\$')    # for command, see issue #7
    return file_name

def z_index(song_infos):
    size = len(song_infos)
    z = len(str(size))
    return z

########################################################

class xiami(object):
    def __init__(self):
        self.dir_ = os.getcwd().decode('utf8')
        self.template_song = 'http://www.xiami.com/song/gethqsong/sid/%s'
        self.template_record = 'http://www.xiami.com/count/playrecord?sid=%s'

        self.collect_id = ''
        self.album_id = ''
        self.artist_id = ''
        self.song_id = ''
        self.user_id = ''
        self.cover_id = ''
        self.cover_data = ''

        self.html = ''
        self.disc_description_archives = {}

        self.download = self.play if args.play else self.download

    def init(self):
        if os.path.exists(cookie_file):
            try:
                t = json.loads(open(cookie_file).read())
                ss.cookies.update(t.get('cookies', t))
                if not self.check_login():
                    print s % (1, 91, '  !! cookie is invalid, please login\n')
                    sys.exit(1)
            except:
                g = open(cookie_file, 'w')
                g.close()
                print s % (1, 97, '  please login')
                sys.exit(1)
        else:
            print s % (1, 91, '  !! cookie_file is missing, please login')
            sys.exit(1)

    def check_login(self):
        #print s % (1, 97, '\n  -- check_login')
        url = 'http://www.xiami.com/task/signin'
        r = ss.get(url)
        if r.content:
            #print s % (1, 92, '  -- check_login success\n')
            self.save_cookies()
            return True
        else:
            print s % (1, 91, '  -- login fail, please check email and password\n')
            return False

    def login(self, email, password):
        print s % (1, 97, '\n  -- login')

        #validate = self.get_validate()
        data = {
            'email': email,
            'password': password,
            #'validate': validate,
            'remember': 1,
            'LoginButton': '登录'
        }

        url = 'http://www.xiami.com/web/login'
        ss.post(url, data=data)
        self.save_cookies()

    # {{{ code from https://github.com/ly0/xiami-tools/blob/master/xiami.py
    def login_taobao(self, username, password):
        print s % (1, 97, '\n  -- login taobao')

        p = {
            "lang": "zh_cn",
            "appName": "xiami",
            "appEntrance": "taobao",
            "cssLink": "",
            "styleType": "vertical",
            "bizParams": "",
            "notLoadSsoView": "",
            "notKeepLogin": "",
            "appName": "xiami",
            "appEntrance": "taobao",
            "cssLink": "https://h.alipayobjects.com/static/applogin/assets/login/mini-login-form-min.css",
            "styleType": "vertical",
            "bizParams": "",
            "notLoadSsoView": "true",
            "notKeepLogin": "true",
            "rnd": str(random.random()),
        }
        url = 'https://passport.alipay.com/mini_login.htm'
        r = ss.get(url, params=p)
        cm = r.content

        data = {
            "loginId": username,
            "password": password,
            "appName": "xiami",
            "appEntrance": "taobao",
            "hsid": re.search(r'"hsid" value="(.+?)"', cm).group(1),
            "cid": re.search(r'"cid" value="(.+?)"', cm).group(1),
            "rdsToken": re.search(r'"rdsToken" value="(.+?)"', cm).group(1),
            "umidToken": re.search(r'"umidToken" value="(.+?)"', cm).group(1),
            "_csrf_token": re.search(r'"_csrf_token" value="(.+?)"', cm).group(1),
            "checkCode": "",
        }
        url = 'https://passport.alipay.com/newlogin/login.do?fromSite=0'
        theaders = headers
        theaders['Referer'] = 'https://passport.alipay.com/mini_login.htm'

        while True:
            r = ss.post(url, data=data, headers=theaders)
            j = r.json()

            if j['content']['status'] == -1:
                if 'titleMsg' not in j['content']['data']: continue
                err_msg = j['content']['data']['titleMsg']
                if err_msg == u'请输入验证码' or err_msg == u'验证码错误，请重新输入':
                    captcha_url = 'http://pin.aliyun.com/get_img?identity=passport.alipay.com&sessionID=%s' % data['cid']
                    tr = ss.get(captcha_url, headers=theaders)
                    path = os.path.join(os.path.expanduser('~'), 'vcode.jpg')
                    with open(path, 'w') as g:
                        img = tr.content
                        g.write(img)
                    print "  ++ 验证码已经保存至", s % (2, 91, path)
                    captcha = raw_input((s % (2, 92, u'  请输入验证码: ')).encode('utf8'))
                    data['checkCode'] = captcha
                    continue

            url = 'http://www.xiami.com/accounts/back?st=%s' % j['content']['data']['st']
            ss.get(url, headers=theaders)

            # delete taobao cookies, only save xiami cookies
            for i in ss.cookies.keys():
                if i not in ('_unsign_token', '_xiamitoken', 'member_auth', 'user'):
                    ss.cookies.__delitem__(i)
            self.save_cookies()
            return
    # }}}

    def get_validate(self):
        url = 'https://login.xiami.com/coop/checkcode?forlogin=1&%s' \
            % int(time.time())
        path = os.path.join(os.path.expanduser('~'), 'vcode.png')
        with open(path, 'w') as g:
            data = ss.get(url).content
            g.write(data)
        print "  ++ 验证码已经保存至", s % (2, 91, path)
        print s % (2, 92, u'  请输入验证码:')
        validate = raw_input()
        return validate

    def save_cookies(self):
        with open(cookie_file, 'w') as g:
            c = {'cookies': ss.cookies.get_dict()}
            g.write(json.dumps(c, indent=4, sort_keys=True))

    def get_durl(self, id_):
        while True:
            try:
                j = ss.get(self.template_song % id_).json()
                t = j['location']
                if not t: return None
                row = t[0]
                encryed_url = t[1:]
                durl = decry(row, encryed_url)
                return durl
            except Exception as e:
                print s % (1, 91, '  |-- Error, get_durl --'), e
                time.sleep(5)

    def record(self, id_):
        ss.get(self.template_record % id_)

    def get_cover(self, info):
        if info['album_name'] == self.cover_id:
            return self.cover_data
        else:
            self.cover_id = info['album_name']
            while True:
                url = info['album_pic_url']
                try:
                    self.cover_data = ss.get(url).content
                    if self.cover_data[:5] != '<?xml':
                        return self.cover_data
                except Exception as e:
                    print s % (1, 91, '   \\\n   \\-- Error, get_cover --'), e
                    time.sleep(5)

    def get_lyric(self, info):
        def lyric_parser(data):
            if len(data) < 10:   # get ' ' from http://img.xiami.net/lyric/1_13772259457649.lrc
                return None

            if re.search(r'\[\d\d:\d\d', data):
                title = ' title: %s\n' % info['song_name'].encode('utf8')
                album = ' album: %s\n' % info['album_name'].encode('utf8')
                artist = 'artist: %s\n' % info['artist_name'].encode('utf8')

                tdict = {}
                for line in data.split('\n'):
                    if re.search(r'^\[\d\d:', line):
                        cn = re.sub(r'\[\d{2}:\d{2}\.\d{2}\]', '', line)
                        time_tags = re.findall(r'\[\d{2}:\d{2}\.\d{2}\]', line)
                        for tag in time_tags: tdict[tag] = cn + '\n'
                time_tags = tdict.keys()
                time_tags.sort()
                data = ''.join([title, album, artist, '\n------------------\n\n'] + \
                               [tdict[tag] for tag in time_tags])
                return data
            else:        # for http://img.xiami.net/lyric/upload/19/1770983119_1356864643.lrc
                return data

        url = 'http://www.xiami.com/song/playlist/id/%s' % info['song_id']
        xml = ss.get(url).content
        t = re.search('<lyric>(http.+?)</lyric>', xml)
        if not t: return None
        lyric_url = t.group(1)
        data = ss.get(lyric_url).content.replace('\r\n', '\n')
        data = lyric_parser(data)
        if data:
            return data.decode('utf8', 'ignore')
        else:
            return None

    def get_disc_description(self, album_url, info):
        if not self.html:
            self.html = ss.get(album_url).content
            t = re.findall(re_disc_description, self.html)
            t = dict([(a, modificate_text(parser.unescape(b.decode('utf8')))) for a, b in t])
            self.disc_description_archives = dict(t)
        if self.disc_description_archives.has_key(info['cd_serial']):
            disc_description = self.disc_description_archives[info['cd_serial']]
            return u'(%s)' % disc_description
        else:
            return u''

    def modified_id3(self, file_name, info):
        id3 = ID3()
        id3.add(TRCK(encoding=3, text=info['track']))
        id3.add(TDRC(encoding=3, text=info['year']))
        id3.add(TIT2(encoding=3, text=info['song_name']))
        id3.add(TALB(encoding=3, text=info['album_name']))
        id3.add(TPE1(encoding=3, text=info['artist_name']))
        id3.add(TPOS(encoding=3, text=info['cd_serial']))
        lyric_data = self.get_lyric(info)
        id3.add(USLT(encoding=3, text=lyric_data)) if lyric_data else None
        #id3.add(TCOM(encoding=3, text=info['composer']))
        #id3.add(WXXX(encoding=3, desc=u'xiami_song_url', text=info['song_url']))
        #id3.add(TCON(encoding=3, text=u'genre'))
        #id3.add(TSST(encoding=3, text=info['sub_title']))
        #id3.add(TSRC(encoding=3, text=info['disc_code']))
        id3.add(COMM(encoding=3, desc=u'Comment', \
            text=info['comment']))
        id3.add(APIC(encoding=3, mime=u'image/jpeg', type=3, \
            desc=u'Front Cover', data=self.get_cover(info)))
        id3.save(file_name)

    def url_parser(self, urls):
        for url in urls:
            if '/collect/' in url:
                self.collect_id = re.search(r'/collect/(\d+)', url).group(1)
                #print(s % (2, 92, u'\n  -- 正在分析精选集信息 ...'))
                self.download_collect()

            elif '/album/' in url:
                self.album_id = re.search(r'/album/(\d+)', url).group(1)
                #print(s % (2, 92, u'\n  -- 正在分析专辑信息 ...'))
                self.download_album()

            elif '/artist/' in url or 'i.xiami.com' in url:
                def get_artist_id(url):
                    html = ss.get(url).content
                    artist_id = re.search(r'artist_id = \'(\d+)\'', html).group(1)
                    return artist_id

                self.artist_id = re.search(r'/artist/(\d+)', url).group(1) \
                    if '/artist/' in url else get_artist_id(url)
                code = raw_input('  >> a  # 艺术家所有专辑.\n' \
                    '  >> r  # 艺术家 radio\n' \
                    '  >> t  # 艺术家top 20歌曲.\n  >> ')
                if code == 'a':
                    #print(s % (2, 92, u'\n  -- 正在分析艺术家专辑信息 ...'))
                    self.download_artist_albums()
                elif code == 't':
                    #print(s % (2, 92, u'\n  -- 正在分析艺术家top20信息 ...'))
                    self.download_artist_top_20_songs()
                elif code == 'r':
                    self.download_artist_radio()
                else:
                    print(s % (1, 92, u'  --> Over'))

            elif '/song/' in url:
                self.song_id = re.search(r'/song/(\d+)', url).group(1)
                #print(s % (2, 92, u'\n  -- 正在分析歌曲信息 ...'))
                self.download_song()

            elif '/u/' in url:
                self.user_id = re.search(r'/u/(\d+)', url).group(1)
                code = raw_input('  >> m   # 该用户歌曲库.\n' \
                    '  >> rm  # 私人电台:来源于"收藏的歌曲","收藏的专辑","喜欢的艺人","收藏的精选集"\n'
                    '  >> rc  # 虾米猜:基于试听行为所建立的个性电台\n  >> ')
                if code == 'm':
                    #print(s % (2, 92, u'\n  -- 正在分析用户歌曲库信息 ...'))
                    self.download_user_songs()
                elif code == 'rm':
                    #print(s % (2, 92, u'\n  -- 正在分析该用户的虾米推荐 ...'))
                    url_rndsongs = url_radio_my
                    self.download_user_radio(url_rndsongs)
                elif code == 'rc':
                    url_rndsongs = url_radio_c
                    self.download_user_radio(url_rndsongs)
                else:
                    print(s % (1, 92, u'  --> Over'))

            elif '/chart/' in url:
                self.chart_id = re.search(r'/c/(\d+)', url).group(1) if '/c/' in url else 101
                type_ = re.search(r'/type/(\d+)', url).group(1) if '/type/' in url else 0
                self.download_chart(type_)

            elif '/genre/' in url:
                if '/gid/' in url:
                    self.genre_id = re.search(r'/gid/(\d+)', url).group(1)
                    url_genre = 'http://www.xiami.com/genre/songs/gid/%s/page/%s'
                elif '/sid/' in url:
                    self.genre_id = re.search(r'/sid/(\d+)', url).group(1)
                    url_genre = 'http://www.xiami.com/genre/songs/sid/%s/page/%s'
                else:
                    print s % (1, 91, '  !! Error: missing genre id at url')
                    sys.exit(1)

                code = raw_input('  >> t  # 风格推荐\n' \
                    '  >> r  # 风格radio\n  >> ')
                if code == 't':
                    self.download_genre(url_genre)
                elif code == 'r':
                    self.download_genre_radio(url_genre)

            else:
                print(s % (2, 91, u'   请正确输入虾米网址.'))

    def get_songs(self, album_id, song_id=None):
        html = ss.get(url_album % album_id).content
        html = html.split('<div id="wall"')[0]
        html1, html2 = html.split('<div id="album_acts')

        t = re.search(r'"v:itemreviewed">(.+?)<', html1).group(1).decode('utf8', 'ignore')
        album_name = modificate_text(t)

        t = re.search(r'"/artist/\d+.+?>(.+?)<', html1).group(1).decode('utf8', 'ignore')
        artist_name = modificate_text(t)

        t = re.findall(r'(\d+)年(\d+)月(\d+)', html1)[0]
        year = '-'.join(t).decode('utf8', 'ignore')

        album_description = ''
        t = re.search(r'专辑介绍：(.+?)<div class="album_intro_toggle">', html2, re.DOTALL)
        if t:
            t = t.group(1)
            t = re.sub(r'<.+?>', '', t).decode('utf8', 'ignore')
            t = parser.unescape(t)
            t = parser.unescape(t)
            t = re.sub(r'\s\s+', u'\n', t).strip()
            t = re.sub(r'<.+?(http://.+?)".+?>', r'\1', t)
            t = re.sub(r'<.+?>([^\n])', r'\1', t)
            t = re.sub(r'<.+?>(\r\n|)', u'\n', t)
            album_description = t

        t = re.search(r'href="(.+?)" id="albumCover"', html1).group(1)
        tt = t.rfind('.')
        t = '%s_4%s' % (t[:tt], t[tt:])
        album_pic_url = t.decode('utf8', 'ignore')

        songs = []
        for c in html2.split('class="trackname"')[1:]:
            disc = re.search(r'>disc (\d+)', c).group(1).decode('utf8', 'ignore')

            t = re.search(r'>disc .+?\[(.+?)\]', c)
            disc_description = modificate_text(t.group(1).decode('utf8', 'ignore')) if t else ''

            t = re.findall(r'"trackid">(\d+)', c)
            tracks = [i.lstrip('0').decode('utf8', 'ignore') for i in t]
            z = len(str(len(tracks)))

            t = re.findall(r'"song_name"><a href="/song/(\d+)".+?>(.+?)</', c)
            song_ids = [i[0].decode('utf8', 'ignore') for i in t]
            song_names = [modificate_text(i[1].decode('utf8', 'ignore')) for i in t]

            if len(tracks) != len(song_ids) != len(song_names):
                print s % (1, 91, '  !! Error: len(tracks) != len(song_ids) != len(song_names)')
                sys.exit(1)

            for i in xrange(len(tracks)):
                song_info = {}
                song_info['song_id'] = song_ids[i]
                song_info['album_id'] = album_id.decode('utf8', 'ignore')
                song_info['song_url'] = u'http://www.xiami.com/song/' + song_ids[i]
                song_info['track'] = tracks[i]
                song_info['cd_serial'] = disc
                song_info['year'] = year
                song_info['album_pic_url'] = album_pic_url
                song_info['song_name'] = song_names[i]
                song_info['album_name'] = album_name
                song_info['artist_name'] = artist_name
                song_info['z'] = z
                song_info['disc_description'] = disc_description
                t = '%s\n\n%s%s' % (song_info['song_url'],
                                    disc_description + u'\n\n' if disc_description else '',
                                    album_description)
                song_info['comment'] = t

                songs.append(song_info)

        cd_serial_auth = int(songs[-1]['cd_serial']) > 1
        for i in xrange(len(songs)):
            z = songs[i]['z']
            file_name = songs[i]['track'].zfill(z) + '.' + songs[i]['song_name'] + \
                ' - ' + songs[i]['artist_name'] + '.mp3'
            if cd_serial_auth:
                songs[i]['file_name'] = ''.join([
                    '[Disc-',
                    songs[i]['cd_serial'],
                    ' # ' + songs[i]['disc_description'] \
                        if songs[i]['disc_description'] else '', '] ',
                    file_name])
            else:
                songs[i]['file_name'] = file_name

        t = [i for i in songs if i['song_id'] == song_id] if song_id else songs
        songs = t

        return songs

    def get_song(self, song_id):
        html = ss.get(url_song % song_id).content
        html = html.split('<div id="wall"')[0]
        album_id = re.search(r'album/(\d+)', html).group(1)
        songs = self.get_songs(album_id, song_id=song_id)
        return songs

    def download_song(self):
        songs = self.get_song(self.song_id)
        print(s % (2, 97, u'\n  >> ' + u'1 首歌曲将要下载.')) \
            if not args.play else ''
        #self.song_infos = [song_info]
        self.download(songs)

    def download_album(self):
        songs = self.get_songs(self.album_id)
        song = songs[0]

        d = song['album_name'] + ' - ' + song['artist_name']
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)

        amount_songs = unicode(len(songs))
        songs = songs[args.from_ - 1:]
        print(s % (2, 97, u'\n  >> ' + amount_songs + u' 首歌曲将要下载.')) \
            if not args.play else ''
        self.download(songs, amount_songs, args.from_)

    def download_collect(self):
        html = ss.get(url_collect % self.collect_id).content
        html = html.split('<div id="wall"')[0]
        collect_name = re.search(r'<h2>(.+?)<', html).group(1).decode('utf8')
        d = collect_name
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)
        song_ids = re.findall('/song/(\d+)" title', html)
        amount_songs = unicode(len(song_ids))
        song_ids = song_ids[args.from_ - 1:]
        print(s % (2, 97, u'\n  >> ' + amount_songs + u' 首歌曲将要下载.')) \
            if not args.play else ''
        n = args.from_
        for i in song_ids:
            songs = self.get_song(i)
            self.download(songs, amount_songs, n)
            self.html = ''
            self.disc_description_archives = {}
            n += 1

    def download_artist_albums(self):
        ii = 1
        album_ids = []
        while True:
            html = ss.get(url_artist_albums % (self.artist_id, str(ii))).content
            t = re.findall(r'/album/(\d+)"', html)
            if album_ids == t: break
            album_ids = t
            if album_ids:
                for i in album_ids:
                    print '  ++ http://www.xiami.com/album/%s' % i
                    self.album_id = i
                    self.download_album()
                    self.html = ''
                    self.disc_description_archives = {}
            else:
                break
            ii += 1

    def download_artist_top_20_songs(self):
        html = ss.get(url_artist_top_song % self.artist_id).content
        song_ids = re.findall(r'/song/(.+?)" title', html)
        artist_name = re.search(r'<p><a href="/artist/\d+">(.+?)<', html).group(1).decode('utf8', 'ignore')
        d = modificate_text(artist_name + u' - top 20')
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)
        amount_songs = unicode(len(song_ids))
        print(s % (2, 97, u'\n  >> ' + amount_songs + u' 首歌曲将要下载.')) \
            if not args.play else ''
        n = 1
        for i in song_ids:
            songs = self.get_song(i)
            self.download(songs, amount_songs, n)
            self.html = ''
            self.disc_description_archives = {}
            n += 1

    def download_artist_radio(self):
        html = ss.get(url_artist_top_song % self.artist_id).content
        artist_name = re.search(r'<p><a href="/artist/\d+">(.+?)<', html).group(1).decode('utf8', 'ignore')

        d = modificate_text(artist_name + u' - radio')
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)

        url_artist_radio = "http://www.xiami.com/radio/xml/type/5/id/%s" % self.artist_id
        n = 1
        while True:
            xml = ss.get(url_artist_radio).content
            song_ids = re.findall(r'<song_id>(\d+)', xml)
            for i in song_ids:
                songs = self.get_song(i)
                self.download(songs, n=n)
                self.html = ''
                self.disc_description_archives = {}
                n += 1

    def download_user_songs(self):
        dir_ = os.path.join(os.getcwd().decode('utf8'), \
            u'虾米用户 %s 收藏的歌曲' % self.user_id)
        self.dir_ = modificate_file_name_for_wget(dir_)
        ii = 1
        n = 1
        while True:
            html = ss.get(url_lib_songs % (self.user_id, str(ii))).content
            song_ids = re.findall(r'/song/(.+?)"', html)
            if song_ids:
                for i in song_ids:
                    songs = self.get_song(i)
                    self.download(songs, n)
                    self.html = ''
                    self.disc_description_archives = {}
                    n += 1
            else:
                break
            ii += 1

    def download_user_radio(self, url_rndsongs):
        d = modificate_text(u'%s 的虾米推荐' % self.user_id)
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)
        n = 1
        while True:
            xml = ss.get(url_rndsongs % self.user_id).content
            song_ids = re.findall(r'<song_id>(\d+)', xml)
            for i in song_ids:
                songs = self.get_song(i)
                self.download(songs, n=n)
                self.html = ''
                self.disc_description_archives = {}
                n += 1

    def download_chart(self, type_):
        html = ss.get('http://www.xiami.com/chart/index/c/%s' % self.chart_id).content
        title = re.search(r'<title>(.+?)</title>', html).group(1).decode('utf8', 'ignore')
        d = modificate_text(title)
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)

        html = ss.get('http://www.xiami.com/chart/data?c=%s&limit=200&type=%s' % (self.chart_id, type_)).content
        song_ids = re.findall(r'/song/(\d+)', html)
        n = 1
        for i in song_ids:
            songs = self.get_song(i)
            self.download(songs, n=n)
            self.html = ''
            self.disc_description_archives = {}
            n += 1

    def download_genre(self, url_genre):
        html = ss.get(url_genre % (self.genre_id, 1)).content
        if '/gid/' in url_genre:
            t = re.search(r'/genre/detail/gid/%s".+?title="(.+?)"' % self.genre_id, html).group(1).decode('utf8', 'ignore')
        elif '/sid/' in url_genre:
            t = re.search(r'/genre/detail/sid/%s" title="(.+?)"' % self.genre_id, html).group(1).decode('utf8', 'ignore')
        d = modificate_text(u'%s - 代表曲目 - xiami' % t)
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)

        n = 1
        page = 2
        while True:
            song_ids = re.findall(r'/song/(\d+)', html)
            if not song_ids: break
            for i in song_ids:
                songs = self.get_song(i)
                self.download(songs, n=n)
                self.html = ''
                self.disc_description_archives = {}
                n += 1
            html = ss.get(url_genre % (self.chart_id, page)).content
            page += 1

    def download_genre_radio(self, url_genre):
        html = ss.get(url_genre % (self.genre_id, 1)).content
        if '/gid/' in url_genre:
            t = re.search(r'/genre/detail/gid/%s".+?title="(.+?)"' % self.genre_id, html).group(1).decode('utf8', 'ignore')
            url_genre_radio = "http://www.xiami.com/radio/xml/type/12/id/%s" % self.genre_id
        elif '/sid/' in url_genre:
            t = re.search(r'/genre/detail/sid/%s" title="(.+?)"' % self.genre_id, html).group(1).decode('utf8', 'ignore')
            url_genre_radio = "http://www.xiami.com/radio/xml/type/13/id/%s" % self.genre_id
        d = modificate_text(u'%s - radio - xiami' % t)
        dir_ = os.path.join(os.getcwd().decode('utf8'), d)
        self.dir_ = modificate_file_name_for_wget(dir_)

        n = 1
        while True:
            xml = ss.get(url_genre_radio).content
            song_ids = re.findall(r'<song_id>(\d+)', xml)
            for i in song_ids:
                songs = self.get_song(i)
                self.download(songs, n=n)
                self.html = ''
                self.disc_description_archives = {}
                n += 1

    def display_infos(self, i, nn, n):
        print '\n  ----------------'
        print '  >>', n, '/', nn
        print '  >>', s % (2, 94, i['file_name'])
        print '  >>', s % (2, 95, i['album_name'])
        print '  >>', 'http://www.xiami.com/song/%s' % i['song_id']
        print '  >>', 'http://www.xiami.com/album/%s' % i['album_id']
        if i['durl_is_H'] == 'h':
            print '  >>', s % (1, 97, 'MP3-Quality:'), s % (1, 91, 'High')
        else:
            print '  >>', s % (1, 97, 'MP3-Quality:'), s % (1, 91, 'Low')
        print ''

    def get_mp3_quality(self, durl):
        if 'm3.file.xiami.com' in durl or 'm6.file.xiami.com' in durl:
            return 'h'
        else:
            return 'l'

    def play(self, songs, nn=u'1', n=1):
        for i in songs:
            self.record(i['song_id'])
            durl = self.get_durl(i['song_id'])
            if not durl:
                print s % (2, 91, '  !! Error: can\'t get durl'), i['song_name']
                continue

            mp3_quality = self.get_mp3_quality(durl)
            i['durl_is_H'] = mp3_quality
            self.display_infos(i, nn, n)
            n = int(n) + 1
            cmd = 'mpv --really-quiet ' \
                '--cache 8146 ' \
                '--user-agent "%s" ' \
                '--http-header-fields="Referer:http://img.xiami.com/static/swf/seiya/1.4/player.swf?v=%s" ' \
                '"%s"' \
                % (headers['User-Agent'], int(time.time()*1000), durl)
            os.system(cmd)
            timeout = 1
            ii, _, _ = select.select([sys.stdin], [], [], timeout)
            if ii:
                sys.exit(0)
            else:
                pass

    def download(self, songs, amount_songs=u'1', n=None):
        dir_ = modificate_file_name_for_wget(self.dir_)
        cwd = os.getcwd().decode('utf8')
        if dir_ != cwd:
            if not os.path.exists(dir_):
                os.mkdir(dir_)

        ii = 1
        for i in songs:
            num = random.randint(0, 100) % 7
            col = s % (2, num + 90, i['file_name'])
            t = modificate_file_name_for_wget(i['file_name'])
            file_name = os.path.join(dir_, t)
            if os.path.exists(file_name):  ## if file exists, no get_durl
                if args.undownload:
                    self.modified_id3(file_name, i)
                    ii += 1
                    n += 1
                    continue
                else:
                    ii += 1
                    n += 1
                    continue

            if not args.undownload:
                if n == None:
                    print(u'\n  ++ download: #%s/%s# %s' \
                        % (ii, amount_songs, col))
                else:
                    print(u'\n  ++ download: #%s/%s# %s' \
                        % (n, amount_songs, col))
                    n += 1

                durl = self.get_durl(i['song_id'])
                if not durl:
                    print s % (2, 91, '  |-- Error: can\'t get durl')
                    continue

                mp3_quality = self.get_mp3_quality(durl)
                if mp3_quality == 'h':
                    print '  |--', s % (1, 97, 'MP3-Quality:'), s % (1, 91, 'High')
                else:
                    print '  |--', s % (1, 97, 'MP3-Quality:'), s % (1, 91, 'Low')

                file_name_for_wget = file_name.replace('`', '\`')
                cmd = 'wget -c -T 5 -nv ' \
                    '-U "%s" ' \
                    '--header "Referer:http://img.xiami.com/static/swf/seiya/1.4/player.swf?v=%s" ' \
                    '-O "%s.tmp" %s' \
                    % (headers['User-Agent'], int(time.time()*1000), file_name_for_wget, durl)
                cmd = cmd.encode('utf8')
                status = os.system(cmd)
                if status != 0:     # other http-errors, such as 302.
                    wget_exit_status_info = wget_es[status]
                    print('\n\n ----###   \x1b[1;91mERROR\x1b[0m ==> \x1b[1;91m%d ' \
                        '(%s)\x1b[0m   ###--- \n\n' % (status, wget_exit_status_info))
                    print s % (1, 91, '  ===> '), cmd
                    sys.exit(1)
                else:
                    os.rename('%s.tmp' % file_name, file_name)

            self.modified_id3(file_name, i)
            ii += 1
            time.sleep(5)

    def _save_do(self, id_, type, tags):
        data = {
            "tags": tags,
            "type": type,
            "id": id_,
            "desc": "",
            "grade": "",
            "share": 0,
            "shareTo": "all",
            "_xiamitoken": ss.cookies['_xiamitoken'],
        }
        url = 'http://www.xiami.com/ajax/addtag'
        r = ss.post(url, data=data)
        j = r.json()
        if j['status'] == 'ok':
            return 0
        else:
            return j['status']

    def save(self, urls):
        tags = args.tags
        for url in urls:
            if '/collect/' in url:
                collect_id = re.search(r'/collect/(\d+)', url).group(1)
                print s % (1, 97, u'\n  ++ save collect:'), 'http://www.xiami.com/song/collect/' + collect_id
                result = self._save_do(collect_id, 4, tags)

            elif '/album/' in url:
                album_id = re.search(r'/album/(\d+)', url).group(1)
                print s % (1, 97, u'\n  ++ save album:'), 'http://www.xiami.com/album/' + album_id
                result = self._save_do(album_id, 5, tags)

            elif '/artist/' in url:
                artist_id = re.search(r'/artist/(\d+)', url).group(1)
                print s % (1, 97, u'\n  ++ save artist:'), 'http://www.xiami.com/artist/' + artist_id
                result = self._save_do(artist_id, 6, tags)

            elif '/song/' in url:
                song_id = re.search(r'/song/(\d+)', url).group(1)
                print s % (1, 97, u'\n  ++ save song:'), 'http://www.xiami.com/song/' + song_id
                result = self._save_do(song_id, 3, tags)

            else:
                print(s % (2, 91, u'   请正确输入虾米网址.'))

            if result == 0:
                print s % (1, 92, '  ++ success.\n')
            else:
                print s % (1, 91, '  !! Error at _save_do.'), result, '\n'

def main(argv):
    if len(argv) < 2:
        sys.exit()

    ######################################################
    # for argparse
    p = argparse.ArgumentParser(description='downloading any xiami.com')
    p.add_argument('xxx', type=str, nargs='*', \
        help='命令对象.')
    p.add_argument('-p', '--play', action='store_true', \
        help='play with mpv')
    p.add_argument('-f', '--from_', action='store', \
        default=1, type=int, \
        help='从第几个开始下载，eg: -f 42')
    p.add_argument('-d', '--undescription', action='store_true', \
        help='no add disk\'s distribution')
    p.add_argument('-t', '--tags', action='store', \
        type=str, default='', help='tags. eg: piano,cello')
    p.add_argument('-n', '--undownload', action='store_true', \
        help='no download, using to renew id3 tags')
    global args
    args = p.parse_args(argv[2:])
    comd = argv[1]
    xxx = args.xxx

    if comd == 'login' or comd == 'g' \
        or comd == 'logintaobao' or comd == 'gt':
        if len(xxx) < 1:
            email = raw_input(s % (1, 97, '  username: ') \
                if comd == 'logintaobao' or comd == 'gt' \
                else s % (1, 97, '     email: '))
            password = getpass(s % (1, 97, '  password: '))
        elif len(xxx) == 1:
            email = xxx[0]
            password = getpass(s % (1, 97, '  password: '))
        elif len(xxx) == 2:
            email = xxx[0]
            password = xxx[1]
        else:
            print s % (1, 91, '  login\n  login email\n  login email password\n  logintaobao\n  logintaobao username\n  logintaobao username password')

        x = xiami()
        if comd == 'logintaobao' or comd == 'gt':
            x.login_taobao(email, password)
        else:
            x.login(email, password)
        is_signin = x.check_login()
        if is_signin:
            print s % (1, 92, '  ++ login succeeds.')
        else:
            print s % (1, 91, '  login failes')

    elif comd == 'signout':
        g = open(cookie_file, 'w')
        g.close()

    elif comd == 'd' or comd == 'download' \
        or comd == 'p' or comd == 'play':
        if comd == 'p' or comd == 'play': args.play = True
        urls = xxx
        x = xiami()
        x.init()
        x.url_parser(urls)

    elif comd == 's' or comd == 'save':
        urls = xxx
        x = xiami()
        x.init()
        x.save(urls)

    else:
        print s % (2, 91, u'  !! 命令错误\n')

if __name__ == '__main__':
    argv = sys.argv
    main(argv)
