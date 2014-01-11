#! /usr/bin/python
# -*- coding: utf-8 -*-

import httplib, urllib, random, re, os, sys, time, subprocess
import logging
import hashlib
from threading import Thread

from urllib2 import Request, urlopen
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer

import mosquitto

import config

thevoices = ['lucy', 'peter', 'rachel', 'heather', 'kenny', 'laura', 'nelly', 'ryan', 'julia', 'sarah', 'klaus', 'de5', 'r2d2']
acapelavoices = ['lucy', 'peter', 'rachel', 'heather', 'kenny', 'laura', 'nelly', 'ryan', 'julia', 'sarah', 'klaus']
googlevoices = ['goo']
attvoices = ["crystal", "mike", "rich", "lauren", "claire", "rosa", "alberto", "klara", "reiner", "alain", "juliette", "arnaud", "charles", "audrey", "anjali"]
txt2phovoices = ['de5']

coutcount = 0
suppressuntil = 0
lastcpamcheck = 0

logger = logging.getLogger('c_out')
hdlr = logging.FileHandler(config.logfile)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr) 
logger.setLevel(logging.INFO)

enabled = 1

def mqtt_connect(client):
    try: 
        client.connect(config.mqtt_server)
        client.subscribe("c_out/+", 1)
        client.on_message = on_message
    except: pass

def mqtt_loop():
    client = mosquitto.Mosquitto(config.mqtt_client_id)
    mqtt_connect(client)
    while True:
        result = client.loop(1)
        if result != 0:
            mqtt_connect(client)
        time.sleep(2)

def on_message(obj, msg):
    if msg.topic == "c_out/play":
        play(msg.payload)
    if msg.topic == "c_out/announce":
        announce(msg.payload)
    if msg.topic == "c_out/random":
        c_out()
    if msg.topic == "c_out/loop":
        play(random.choice(loop_sounds()))
    if msg.topic == "c_out/tts":
        tts("julia", msg.payload)
    if msg.topic == "c_out/julia":
        tts("julia", msg.payload)
    if msg.topic == "c_out/klaus":
        tts("klaus", msg.payload)
    if msg.topic == "c_out/r2d2":
        r2d2(msg.payload)
    print("%s: %s" % (msg.topic, msg.payload))

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
    mqtt = Thread(target=mqtt_loop)
    mqtt.start()
    if config.jsonrpc_enabled:
        start_jsonrpc_server()


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
    oFile = open('%s/%s.mp3' % (config.tmpdir, outfile),'wb')
    oFile.close

    for mp3 in mp3s:
        iFile = open("%s/%s" % (config.r2d2path, mp3), 'r')
        oFile.write(iFile.read())
        iFile.close
    oFile.close

    return "%s/%s" % (config.tmpdir, outfile)


def tts(voice, text):
    if iscpam():
        return "cpam alarm. bitte beachten sie die sicherheitshinweise. (%d)" % (suppressuntil - int(time.time()))
    if voice in acapelavoices:
        return playfile(acapela(voice, text))
    if voice in googlevoices:
        return playfile(googleTTS(text))
    if voice in txt2phovoices:
        return playfile(txt2pho(voice, text))
    elif voice == 'r2d2':
        return playfile(r2d2(text))
    else:
        return playfile(acapela('julia', text))

def acapela(voice, text):
    pitch = 100
    speed = 180
    
    if not text.endswith("."): text = "%s." % (text,)

    text = text.replace('$','Dollar')
    if (voice in ['julia', 'sarah', 'klaus']):
        #text = text.replace('c-base','zieh baejs')
        text = text.replace('c-base','ziebays')
        text = text.replace('c-beam','ziebiem')
        text = text.replace('c3pb', 'zeh drei p b')

    if voice.find('22k') == -1:
        voice = '%s22k' % voice
    
    basename = '%s_%s_%d_%d' % (urllib.quote(text.lower()), voice, pitch, speed)
    filename = '%s/%s.mp3' % (config.tmpdir, hashlib.sha256(basename).hexdigest())
    textparam = '\\vct=%d\\ \\spd=%d\\ %s' % (pitch, speed, text)

    # check whether we have a cached version of the the file
    if os.path.isfile(filename):
        logger.info('%s - %s' % (text, filename))
        return filename
    else:
        params = urllib.urlencode({
            'cl_env': 'FLASH_AS_3.0',
            'req_asw_type': 'INFO',
            'req_voice': voice,
            'req_timeout': '120',
            'cl_vers': '1-30',
            'req_snd_type': '',
            'req_text': textparam,
            'cl_app': 'PROD',
            'cl_login': 'ACAPELA_BOX',
            'prot_vers': '2',
            'req_snd_id': '0_0_84%s88' % random.randint(0, 32767),
            'cl_pwd': config.acapelapassword
        })

        headers = {"Content-type": "application/x-www-form-urlencoded",
                  "Accept": "text/plain"}
        conn = httplib.HTTPConnection("vaassl3.acapela-group.com")
        conn.request("POST", "/Services/AcapelaBOX/0/Synthesizer", params, headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()

        url = re.compile('http://.*\.mp3').search(data).group()

        mysock = urllib.urlopen(url)
        fileToSave = mysock.read()
        oFile = open('%s' % filename,'wb')
        oFile.write(fileToSave)
        oFile.close
        logger.info('%s - %s' % (text, filename))
        return filename



def googleTTS(text, lang="de", encoding="UTF-8", useragent="firefox"):
    basename = '%s_%s' % (urllib.quote(text.lower()), lang)
    filename = '%s/%s.mp3' % (config.tmpdir, hashlib.sha256(basename).hexdigest())

    logger.info('%s - %s' % (text, filename))
    if os.path.isfile(filename):
        return filename
    else:
	    reqObj = Request("http://translate.google.com/translate_tts?ie=" + encoding + "&tl=" + lang + "&q=" + text, headers={ 'user-agent':useragent })
	
	    fileObj = urlopen(reqObj)
	    localFile = open(filename, "wb")
	    localFile.write(fileObj.read())
	    localFile.close()

    return filename

def att(voice, text):
    return
    HOST = "192.20.225.55"
    basename = '%s_%s' % (urllib.quote(text.lower()), lang)
    filename = '%s/%s.mp3' % (config.tmpdir, hashlib.sha256(basename).hexdigest())
    params = urllib.urlencode({'voice': voice, 'txt':text, 'speakButton': 'SPEAK'})
    headers = {"Content-type": "application/x-www-form-urlencoded",
            "User-Agent": "firefox",
            "Accept": "text/plain"}
    conn = httplib.HTTPConnection(HOST)
    conn.request("POST", "/tts/cgi-bin/nph-talk", params, headers)
    response = conn.getresponse()
    if response.status != 301:
        print("http cgi error, cant get wav url (status=%s)" % response.status)
        raise Exception

    path = response.getheader('Location')
    conn.close()

    mysock = urllib.urlopen("http://%s/%s" % (HOST, path))
    fileToSave = mysock.read()
    oFile = open('%s' % filename,'wb')
    oFile.write(fileToSave)
    oFile.close
    logger.info('%s - %s' % (text, filename))
    return filename

def r2d2(text):
    mp3s = []

    for char in text:
        char = char.replace(" ", "space")
        char = char.replace("\n", "space")
        char = char.replace("/", "slash")
        char = char.replace("-", "minus")
        char = char.replace("?", "ask")
        char = char.replace(unicode('\xc3\xa4', 'utf8'), "ae")
        char = char.replace(unicode('\xc3\x9e', 'utf8'), "szett")
        char = char.replace(unicode('\xc3\xb6', 'utf8'), "oe")
        char = char.replace(unicode('\xc3\xbc', 'utf8'), "ue")
        char = char.replace(unicode('\xc3\x84', 'utf8'), "AE")
        char = char.replace(unicode('\xc3\x96', 'utf8'), "OE")
        char = char.replace(unicode('\xc3\x9c', 'utf8'), "UE")

        mp3s.append("%s/%s.mp3" % (config.r2d2path, char))
    logger.info("%s - %s" % (text, "r2d2"))
    return " ".join(mp3s)

def txt2pho(voice, text):
    filenamemp3 = '%s/%s_%s.mp3' % (config.tmpdir, urllib.quote(text.lower()), voice)
    filenamewav = '%s/%s_%s.wav' % (config.tmpdir, urllib.quote(text.lower()), voice)
    os.system('echo "%s" | %s/txt2pho | %s/mbrola -v 2.5 %s/data/%s/%s - %s' % (text, config.txt2phopath, config.txt2phopath, config.txt2phopath, voice, voice, filenamewav))
    os.system('lame %s %s' % (filenamewav, filenamemp3))
    return filenamemp3

def getvolume():
    res = subprocess.Popen(['amixer', 'get', 'Master'],  stdout=subprocess.PIPE).stdout.read()
    m = re.search('\[(\d+)\%\]', res)
    try:
        curvol = m.group(1)
    except:
        curvol = -1

    #curvol = subprocess.Popen('/usr/local/bin/getvol', stdout=subprocess.PIPE).stdout.read()
    return curvol

def setvolume(vol):
    os.system('amixer set Master %s%%' % vol)
    return getvolume()

def c_out():
    return play(random.choice(sounds()))

#def c_out(sound):
#    return play(sound)

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

def playfile(filename):
    global enabled
    if filename.find(".") == -1:
        filename = "%s.mp3" % filename
    if filename.find("/") == -1:
        filename = findFile(config.sampledir, filename)
    if config.player == 'mplayer':
        print('mplayer -af volume=+5 -softvol -really-quiet %s >/dev/null' % filename)
        #if enabled == 1: os.system('mplayer -af -softvol -really-quiet %s >/dev/null' % filename)
        if enabled == 1: os.system('killall mplayer; mplayer %s >/dev/null &' % filename)
    else:
        if enabled == 1: os.system('%s %s &' % (player, filename))
    return "aye"

def announce(text):
    """Plays a ringing sound, says an announcement and then repeats it."""
    if iscpam(): 
        return "cpam alarm. bitte beachten sie die sicherheitshinweise. (%d)" % (suppressuntil - int(time.time()))
    files = ["%s/announce.mp3" % config.sampledir,
        acapela('julia', "Achtung! Eine wichtige Durchsage:"),
        acapela('julia', "%s." % text),
        acapela('julia', 'Ich wiederhole:'),
        acapela('julia', "%s." % text),
        acapela('julia', 'Vielen Dank!') ]
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

