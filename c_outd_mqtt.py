#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import http.client
import json
import logging
import os
import random
import re
import ssl
import subprocess
import sys
import time
from threading import Lock, Thread
from urllib.parse import quote, unquote, urlencode
from urllib.request import Request, urlopen

import paho.mqtt.client as paho
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer

import config

thevoices = ['de5', 'r2d2']
googlevoices = ['goo']
attvoices = ["crystal", "mike", "rich", "lauren", "claire", "rosa", "alberto", "klara", "reiner", "alain", "juliette", "arnaud", "charles", "audrey", "anjali"]
txt2phovoices = ['de5']

coutcount = 0
suppressuntil = 0
lastcpamcheck = 0

logger = logging.getLogger('c_out')
hdlr = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr)
logger.setLevel(logging.INFO)

enabled = 1

def mqtt_connect(client):
    try:
        client.username_pw_set(config.mqtt_client_name, password=config.mqtt_client_password)
        if config.mqtt_server_tls:
            logger.debug(client.tls_set(config.mqtt_server_cert, cert_reqs=ssl.CERT_OPTIONAL))
            logger.debug(client.connect(config.mqtt_server, port=1884))
        else:
            logger.debug(client.connect(config.mqtt_server, port=1883))
        client.subscribe("c_out/+", 1)
        client.subscribe("bar/+", 1)
        client.on_message = on_message
    except Exception as e:
        logger.error(e)

def mqtt_loop():
    client = paho.Client(paho.CallbackAPIVersion.VERSION2, config.mqtt_client_id)
    mqtt_connect(client)
    while True:
        result = client.loop(1)
        if result != 0:
            mqtt_connect(client)
        time.sleep(2)

def extract_payload(payload):
    try:
        return json.loads(payload)
    except ValueError:
        return payload

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode('utf-8', errors='replace')
    logger.info("Got a message via MQTT!")
    logger.info("Message on %s, payload: %s" % (topic, payload))
    if topic == "c_out/play":
        play(payload)
    if topic == "c_out/announce":
        announce(extract_payload(payload))
    if topic == "c_out/announce_en":
        announce_en(extract_payload(payload))
    if topic == "c_out/random":
        c_out()
    if topic == "c_out/loop":
        play(random.choice(loop_sounds()))
    if topic == "c_out/tts" or topic == "c_out/julia":
        logger.info("Calling pico")
        playfile(pico2wave(payload))
    if topic.lower() == "c_out/r2d2":
        r2d2(payload)
    if topic.lower() == "bar/status":
        play("meep.mp3")
    logger.debug("%s: %s" % (topic, payload))

def start_jsonrpc_server():
    server = SimpleJSONRPCServer(('0.0.0.0', 1775))

    server.register_function(tts, 'tts')
    server.register_function(r2d2, 'r2d2')
    server.register_function(play, 'play')
    server.register_function(setvolume, 'setvolume')
    server.register_function(getvolume, 'getvolume')
    server.register_function(voices, 'voices')
    server.register_function(sounds, 'sounds')
    server.register_function(loop_sounds, 'loop_sounds')
    server.register_function(c_out, 'c_out')
    server.register_function(announce, 'announce')
    server.register_function(enable, 'enable')
    server.register_function(disable, 'disable')
    server.serve_forever()


def main():
    mqtt = Thread(target=mqtt_loop, daemon=True)
    mqtt.start()
    if config.jsonrpc_enabled:
        start_jsonrpc_server()
    else:
        mqtt.join()


def voices():
    return thevoices


def listFiles(dir):
    ls = []
    for item in os.listdir(dir):
        if os.path.isdir("%s/%s" % (dir, item)):
            ls.extend(listFiles("%s/%s" % (dir, item)))
        else:
            ls.append(item)
    return ls


def findFile(dir, filename):
    for item in os.listdir(dir):
        if os.path.isfile("%s/%s" % (dir, item)):
            if item.find(filename) != -1:
                return "%s/%s" % (dir, item)
        elif os.path.isdir("%s/%s" % (dir, item)):
            res = findFile("%s/%s" % (dir, item), filename)
            if res != "":
                return res
    return ""


def mergemp3(mp3s, outfile):
    with open('%s/%s.mp3' % (config.tmpdir, outfile), 'wb') as oFile:
        for mp3 in mp3s:
            with open("%s/%s" % (config.r2d2path, mp3), 'rb') as iFile:
                oFile.write(iFile.read())

    return "%s/%s" % (config.tmpdir, outfile)


def cachefilename(text, suffix):
    return '%s/%s' % (config.tmpdir, hashlib.sha256(text.encode('utf-8')).hexdigest() + suffix)


def tts(voice, text):
    if iscpam():
        return "cpam alarm. bitte beachten sie die sicherheitshinweise. (%d)" % (suppressuntil - int(time.time()))
    if voice in googlevoices:
        return playfile(googleTTS(text))
    if voice in txt2phovoices:
        return playfile(txt2pho(voice, text))
    elif voice == 'r2d2':
        return playfile(r2d2(text))
    else:
        return playfile(pico2wave(text))

def googleTTS(text, lang="de", encoding="UTF-8", useragent="firefox"):
    basename = '%s_%s' % (quote(text.lower()), lang)
    filename = cachefilename(basename, '.mp3')

    logger.info('%s - %s' % (text, filename))
    if os.path.isfile(filename):
        return filename

    reqObj = Request("http://translate.google.com/translate_tts?ie=" + encoding + "&tl=" + lang + "&q=" + quote(text), headers={'user-agent': useragent})
    with urlopen(reqObj) as fileObj, open(filename, "wb") as localFile:
        localFile.write(fileObj.read())

    return filename

def pico2wave(text, language="de-DE"):
    replaced = ''.join([i if ord(i) < 128 else '_' for i in text])
    basename = '%s_%s' % (quote(replaced.lower()), language)
    filename = cachefilename(basename, '.wav')
    # check whether we have a cached version of the the file
    if os.path.isfile(filename):
        logger.info('%s - %s' % (text, filename))
        return filename
    subprocess.run(["/usr/bin/pico2wave", "--lang=%s" % language, "--wave=%s" % filename, text])
    return filename


def att(voice, text):
    return
    HOST = "192.20.225.55"
    basename = '%s_%s' % (quote(text.lower()), voice)
    filename = cachefilename(basename, '.mp3')
    params = urlencode({'voice': voice, 'txt': text, 'speakButton': 'SPEAK'})
    headers = {"Content-type": "application/x-www-form-urlencoded",
            "User-Agent": "firefox",
            "Accept": "text/plain"}
    conn = http.client.HTTPConnection(HOST)
    conn.request("POST", "/tts/cgi-bin/nph-talk", params, headers)
    response = conn.getresponse()
    if response.status != 301:
        logger.error("http cgi error, cant get wav url (status=%s)" % response.status)
        raise Exception

    path = response.getheader('Location')
    conn.close()

    with urlopen("http://%s/%s" % (HOST, path)) as mysock, open(filename, 'wb') as oFile:
        oFile.write(mysock.read())
    logger.info('%s - %s' % (text, filename))
    return filename

R2D2_CHARS = {
    " ": "space",
    "\n": "space",
    "/": "slash",
    "-": "minus",
    "?": "ask",
    "ä": "ae",
    "ß": "szett",
    "ö": "oe",
    "ü": "ue",
    "Ä": "AE",
    "Ö": "OE",
    "Ü": "UE",
}

def r2d2(text):
    mp3s = []

    for char in text:
        char = R2D2_CHARS.get(char, char)
        mp3s.append("%s/%s.mp3" % (config.r2d2path, char))
    logger.info("%s - %s" % (text, "r2d2"))
    return " ".join(mp3s)

def txt2pho(voice, text):
    filenamemp3 = '%s/%s_%s.mp3' % (config.tmpdir, quote(text.lower()), voice)
    filenamewav = '%s/%s_%s.wav' % (config.tmpdir, quote(text.lower()), voice)
    os.system('echo "%s" | %s/txt2pho | %s/mbrola -v 2.5 %s/data/%s/%s - %s' % (text, config.txt2phopath, config.txt2phopath, config.txt2phopath, voice, voice, filenamewav))
    os.system('lame %s %s' % (filenamewav, filenamemp3))
    return filenamemp3

def getvolume():
    try:
        res = subprocess.run(['amixer', 'get', 'Master'], capture_output=True, text=True).stdout
        m = re.search(r'\[(\d+)%\]', res)
        curvol = m.group(1)
    except Exception:
        curvol = -1

    return curvol

def setvolume(vol):
    os.system('amixer set Master %s%%' % vol)
    return getvolume()

def c_out():
    return play(random.choice(sounds()))

def sounds():
    return listFiles(config.sampledir)

def loop_sounds():
    return listFiles("%s/loop" % config.sampledir)

def iscpam():
    global coutcount
    global suppressuntil
    global lastcpamcheck
    now = int(time.time())
    if lastcpamcheck + config.cpamdelta > now:
        coutcount += 1
    else:
        coutcount = 1
    lastcpamcheck = now
    if coutcount > config.c_outlimit:
        if suppressuntil == 0:
            suppressuntil = now + config.suppressiontimeout
            return True
        elif now > suppressuntil:
            coutcount = 1
            suppressuntil = 0
            return False
        else:
            return True
    else:
        return False

def play(filename):
    if iscpam():
        return "cpam alarm. bitte beachten sie die sicherheitshinweise. (%d)" % (suppressuntil - int(time.time()))
    else:
        return playfile(filename)

_play_lock = Lock()
_play_gen = 0
_play_proc = None

def player_cmd(filename):
    if config.player == 'mplayer':
        return ['/usr/bin/mplayer', '-af', 'volume=+5', '-softvol', '-really-quiet', filename]
    if config.player == 'omxplayer':
        return ['omxplayer', filename]
    return [config.player, filename]

def stop_playback():
    """Stops the running player and invalidates any queued files.
    Returns the new playback generation."""
    global _play_gen, _play_proc
    with _play_lock:
        _play_gen += 1
        if _play_proc is not None and _play_proc.poll() is None:
            _play_proc.kill()
        return _play_gen

def play_sequence(files, gen):
    """Plays files one after another, each in its own player process, so
    the player drains the audio buffer before the next file starts."""
    global _play_proc
    for f in files:
        with _play_lock:
            if gen != _play_gen:
                return
            logger.debug(" ".join(player_cmd(f)))
            try:
                proc = subprocess.Popen(player_cmd(f), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError as e:
                logger.error("cannot start player: %s" % e)
                return
            _play_proc = proc
        proc.wait()

def resolve_sound(filename):
    if filename.find(".") == -1:
        filename = "%s.mp3" % filename
    if filename.find("/") == -1:
        filename = findFile(config.sampledir, filename)
    return filename

def playfile(filename):
    """Plays one file or several space-separated files in sequence."""
    if filename is None:
        return "playfile got None"
    files = [resolve_sound(f) for f in filename.split()]
    if enabled == 1 and files:
        gen = stop_playback()
        Thread(target=play_sequence, args=(files, gen), daemon=True).start()
    return "aye"

def announce(text):
    """Plays a ringing sound, says an announcement and then repeats it."""
    if iscpam():
        return "cpam alarm. bitte beachten sie die sicherheitshinweise. (%d)" % (suppressuntil - int(time.time()))
    text = unquote(str(text))
    files = [
        "%s/announce.mp3" % config.sampledir,
        pico2wave("Achtung! Eine wichtige Durchsage:"),
        pico2wave("%s." % text),
        pico2wave('Ich wiederhole:'),
        pico2wave("%s." % text),
        pico2wave('Vielen Dank!')
    ]
    playfile(" ".join(files))
    return "aye"

def announce_en(text):
    """Plays a ringing sound, says an announcement and then repeats it. In English!"""
    if iscpam():
        return "cpam alarm. bitte beachten sie die sicherheitshinweise. (%d)" % (suppressuntil - int(time.time()))
    files = [
        "%s/announce_fritz.mp3" % config.sampledir,
        pico2wave("%s." % text, 'en-US')
    ]
    playfile(" ".join(files))
    return "aye"


def disable():
    global enabled
    enabled = 0
    return "disabled"

def enable():
    global enabled
    enabled = 1
    return "enabled"

if __name__ == "__main__":
    main()
