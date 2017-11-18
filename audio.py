import discord
from discord.ext import commands
import threading
import os
from random import shuffle, choice
from cogs.utils.dataIO import dataIO
from cogs.utils import checks
from cogs.utils.chat_formatting import pagify, escape
from urllib.parse import urlparse
from __main__ import send_cmd_help, settings
from json import JSONDecodeError
import re
import logging
import collections
import copy
import asyncio
import math
import time
import inspect
import subprocess
import urllib.parse

#IMPORTANT ?
import youtube_dl

youtube_dl_options = {
    'source_address': '0.0.0.0',
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat':'mp3',
    'nocheckcertificate':True,
    'ignoreerrors':False,
    'quiet':True,
    'no_warnings':True,
    'outtmpl':'data/audio/shared/%(id)s',
    'default_search':'auto',
    'encoding':'utf-8'
}

def display_time(seconds):
    return "**{}:{}**".format(seconds//60, seconds%60)

class Maudio:
    def __init__(self, bot):
        self.bot = bot
        self.playlist = {}
        self.downloaders = []
        self.bot_players = []
        self.settings = dataIO.load_json("data/audio/shared/settings.json")
        self.bot_players.append(self.bot)
        self.playlist = {self.bot:[]}
        self.skip_votes = {self.bot:[]}
        #self.iron = self.bot.get_cog("Iron")
        #self.silver = self.bot.get_cog("Silver")
        #self.gold = self.bot.get_cog("Gold")
        #self.platinum = self.bot.get_cog("Platinum")
        #try:
        #    self.add_all_bots()
        #except:
        #    pass
        self.tempshit = False
    def add_all_bots(self):
        self.bot_players.append(self.iron.bot)
        self.bot_players.append(self.silver.bot)
        self.bot_players.append(self.gold.bot)
        self.bot_players.append(self.platinum.bot)
        self.playlist = {
            self.iron: [],
            self.silver: [],
            self.gold: [],
            self.platinum: [],
            self.bot:[]
        }

    @commands.command(pass_context=True)
    async def set_vol(self, ctx, volume:int=None):
        """The command to set the volume

        It can go up to 200 but at 200 you should expect clipping."""
        if not volume:
            await self.bot.say("Current volume : {}".format(self.settings["VOLUME"]))
            return
        if volume > 200 or volume < 0:
            await self.bot.say("Invalid volume.")
        else:
            volume/=100
            self.settings["VOLUME"] = volume
            for i in self.bot_players:
                i.voice_client_in(ctx.message.server).audio_player.volume = volume
    @commands.command(pass_context=True)
    @checks.is_owner()
    async def set_bots(self, ctx):
        try:
            self.add_all_bots()
        except:
            await self.bot.say("There was an error while adding bots. Don't know "
                "what happened and my creator is kind of lazy so git gud bitsh.")
    @commands.command(pass_context=True)
    @checks.is_owner()
    async def dc_all(self, ctx):

        for player in self.bot_players:
            if player == self.bot:
                continue
            await player.send_message(ctx.message.channel, "Disconnecting {}".format(player.user.name))

            await player.logout()
            del player
    async def _join_voice_channel(self, player, channel):
        try:
            await asyncio.wait_for(player.join_voice_channel(channel), timeout=5, loop=player.loop)
        except asyncio.futures.TimeoutError:
            await self.bot.say("Bot failed to connect to voice channel, try again in 10 mins.")


    async def _create_ffmpeg_player(self, player,channel, song, start_time=None, end_time=None):
        server = channel.server
        voice_channel = self.playlist[player][0][0]
        voice_client = player.voice_client_in(server)
        if voice_client is None:
            to_connect = voice_channel
            if to_connect is None:
                #raise VoiceNotConnected("Okay somehow we're not connected and "
                #                        "we have no valid channel to "
                #                        "reconnect. In other words...LOL "
                #                        "REKT.")
                pass
            await self._join_voice_channel(player, to_connect)
            voice_client = player.voice_client_in(server)

        if voice_client.channel != voice_channel:
            await self._join_voice_channel(player, voice_channel)

        file_name = os.path.join("data/audio/shared", song.id)
        use_avconv = self.settings["AVCONV"]
        options = '-b:a 64k -bufsize 64k'
        before_options = ""
        if start_time:
            before_options += '-ss {}'.format(start_time)
        if end_time:
            options +=" -to {} -copyts".format(end_time)

        try:
            voice_client.audio_player.process.kill()
        except AttributeError:
            pass
        except ProcessLookupError:
            pass

        voice_client.audio_player = voice_client.create_ffmpeg_player(file_name, use_avconv=use_avconv, options=options, before_options=before_options)

        vol = self.settings["VOLUME"] / 100
        voice_client.audio_player.volume = vol

        return voice_client

    def garantee_bot(self,song,channel):
        player = None
        #player = discord.utils.find(lambda x: x.voice_client_in(channel.server).channel == channel, self.bot_players)
        for i in self.bot_players:
            if i.user in channel.voice_members:
                player = i
                break

        if player:
            if len(self.playlist[player])>=4:
                return
            return player

        player = discord.utils.find(lambda x: self.playlist[x] == [], self.bot_players)
        if player:
            return player

        ls = []
        for x in self.bot_players:
            ls.append((sum(j.duration for i,j in self.playlist[x]),x))
        return min(ls,key=lambda y: y[0])[1]


    @commands.command(pass_context=True, no_pm=True)
    async def adl(self, ctx, *, url_or_search_terms):
        url = url_or_search_terms
        server = ctx.message.server
        author = ctx.message.author
        voice_channel = author.voice_channel
        channel = ctx.message.channel

        voice_channel = author.voice.voice_channel
        #if voice_channel is None:
        #    await self.bot.say("You're currently not inside a voice channel.")
        #    return
        url = url.strip("<>")

        if not url.startswith("https://"):
            url = url.replace("/","&%47")
            url = "[0x0E74D3C]" + url

        if url not in url and "youtube" in url:
            parsed_url = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed_url.query)
            query.pop("list",None)
            parsed_url = parsed_url.replace(query=urllib.parse.urlencore(query,True))
            url = urllib.parse_urlunparse(parsed_url)

        if self.downloaders:
            dl = Downloader(url)
            self.downloaders.append(dl)
            while self.downloaders[0].is_alive():
                if dl == self.downloaders[0]:
                    break
                await asyncio.sleep(5)


        else:
            dl = Downloader(url, download=True)
            self.downloaders.append(dl)
        dl.get_info()
        sng = dl.song
        e = discord.Embed(title=sng.title,color=0xFFFFFF, url=sng.url).set_footer(text=sng.url)

        player = self.garantee_bot(sng, author.voice.voice_channel)

        est_time = sum(x[1].duration for x in self.playlist[player])
        e.set_image(url=sng.thumbnail)
        e.add_field(name="Duration: ", value=display_time(sng.duration))
        e.add_field(name="Views: ", value="**{}**".format(sng.view))
        e.add_field(name="Estimated to play in: ", value=est_time)
        e.add_field(name="Place in queue: ",value=len(self.playlist[player])+1)
        await self.bot.say(embed=e)
        #self.temporary = dl.song


        dl.run()
        dl.done.wait()
        self.playlist[player].append((author.voice.voice_channel, sng))
        self.downloaders.pop(0)

    def is_playing(self,player,server): #.voice
        if not player.is_voice_connected(server):
            return False
        if player.voice_client_in(server) is None:
            return False
        if not hasattr(player.voice_client_in(server),"audio_player"):
            return False
        if player.voice_client_in(sever).audio_player.is_done():
            return False

        return True

    async def _play(self, player, channel, song, **kwargs):
        voice_client = await self._create_ffmpeg_player(player, channel, song, **kwargs)
        return voice_client

    async def queue_manager(self, player):
        channel = self.playlist[player][0][0]
        server = channel.server
        queue = self.playlist[player]
        song = queue[0][1]
        print(self.is_playing(player,server))
        if not self.is_playing(player,server):
            self.skip_votes[player] = []
            voice_client = await self._play(player, channel, song)
            voice_client.audio_player.start()
            self.playlist[player].pop(0)
    async def song_is_finished(self, player, server):
        while not player.voice_client_in(server).audio_player.is_done():
            await asyncio.sleep(0.5)
        return True


    async def queue_scheduler(self):
        while self == self.bot.get_cog('Maudio'):
            tasks = []
            queue = self.playlist
            #temp_queue = copy.deepcopy(self.tempqueue)
            for acc,pl in queue.items():
                if len(pl) == 0:# and len(temp_queue[acc]) == 0
                    continue

                tasks.append(self.bot.loop.create_task(self.queue_manager(acc)))
            completed = [t.done() for t in tasks]
            while not all(completed):
                completed = [t.done() for t in tasks]
                await asyncio.sleep(0.5)
            await asyncio.sleep(1)

    async def reload_monitor(self):
        while self == self.bot.get_cog('Maudio'):
            await asyncio.sleep(1)

        for acc in self.bot_players:
            for vc in acc.voice_clients:
                try:
                    vc.audio_player.stop()
                except:
                    pass


class Downloader(threading.Thread):
    def __init__(self, url, download=False, *args, **kwargs):
        super().__init__(*args,**kwargs)
        self.url = url
        self.done = threading.Event()
        self.song = None
        self._download = download
        self._yt = None
        self.error = None

    def search(self):
        if self._yt is None:
            self._yt = youtube_dl.YoutubeDL(youtube_dl_options)
        if "[0x0E74D3C]" not in self.url:
            video = self._yt.extract_info(self.url, download=False, process=False)
        else:
            self.url = self.url[11:]
            search_list = self._yt.extract_info(self.url, download=False)
            if not "entries" in yt_id.keys():
                video = self._yt.extract_info("https://youtube.com/watch?v={}".format(search_list["id"]), download=False)
                self.song = Song(**video)
                return self.song
            return search_list["entries"]
    def run(self):
        self.get_info()
        if self._download:
            self.download()
        #except youtub_dl.utils.DownloadError as e:
        #    self.error = str(e)
        #except OSError as e:
        #    log.warning("Os error while downloading '{}':\n{}".format(self.url, str(e)))
        self.done.set()

    def download(self):
        if not os.path.isfile("data/audio/shared"+self.song.id):
            video = self._yt.extract_info(self.url)
            self.song = Song(**video)

    def get_info(self):
        if self._yt is None:
            self._yt = youtube_dl.YoutubeDL(youtube_dl_options)
        if "[0x0E74D3C]" not in self.url:
            video = self._yt.extract_info(self.url, download=False, process=False)
        else:
            self.url = self.url[11:]
            yt_id = self._yt.extract_info(self.url, download=False)
            if yt_id.get("entries"):
                yt_id = yt_id["entries"][0]["id"]

            self.url = "https://youtube.com/watch?v={}".format(yt_id)
            video = self._yt.extract_info(yt_id, download=False)

        if video is not None:
            self.song = Song(**video)
class Song:
    def __init__(self, **kwargs):
        self.__dict__ = kwargs
        self.view = kwargs.pop('view_count',None)
        self.description = kwargs.pop('description',None)
        self.likes = kwargs.pop('like_count',None)
        self.thumbnail = kwargs.pop('thumbnail',None)
        self.dislikes = kwargs.pop('dislike_count',None)
        self.view = kwargs.pop('view',None)
        self.title = kwargs.pop('title',None)
        self.id = kwargs.pop('id',None)
        self.url = kwargs.pop('webpage_url',None)
        self.uploader = kwargs.pop('uploader',None)
        self.duration = kwargs.pop('duration',60)
        self.start_time = kwargs.pop('start_time',None)
        self.end_time = kwargs.pop('end_time',None)

def check_folder():
    folders = ("data/audio","data/audio/shared")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating {} folder.....".format(folder))
            os.makedirs(folder)

def check_files():
    check_folder()
    default = {"VOLUME":50, "AVCONV":False, "VOTE_THRESHOLD":50}
    settings_path = "data/audio/shared/settings.json"

    if not os.path.isfile(settings_path):
        print("Creating default audio settings.json...")
        dataIO.save_json(settings_path, default)
    else:
        try:
            current = dataIO.load_json(settings_path)
        except JSONDecodeError:
            dataIO.save_json(settings_path, default)
            current = dataIO.load_json(settings_path)
        if current.keys() != default.keys():
            for key in default.keys():
                if key not in current.keys():
                    current[key] = default[key]
                    print(
                        "Adding {} field to audio settings.json...".format(key)
                    )
            dataIO.save_json(settings_path, current)

def setup(bot):
    check_files()
    n = Maudio(bot)
    bot.add_cog(n)
    bot.loop.create_task(n.reload_monitor())
    bot.loop.create_task(n.queue_scheduler())
