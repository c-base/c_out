#! /usr/bin/python
# -*- coding: utf-8 -*-

mqtt_client_id = "c_out_nerdctrl"
mqtt_server = "c-beam.cbrp3.c-base.org"
mqtt_server_tls = False
#mqtt_server_cert = "/etc/ssl/certs/class3.crt"
#mqtt_server_cert = "/etc/ssl/certs/c-beam-ext.c-base.org.pem"
#mqtt_server_cert = "/etc/ssl/certs/c-beam-mqtt.crt"
mqtt_server_cert = "/etc/ssl/certs/root.crt"
mqtt_client_name = "nerdctrl"
mqtt_client_password = "ejwfoiwejfwofijf38fu98f1hfnwevlkwenvlwevjn"
jsonrpc_enabled = True

#player = 'mpg123'
player = 'mplayer'

c_outlimit = 10
suppressiontimeout = 300
cpamdelta = 90

#sampledir = '/usr/local/sounds/loop'
sampledir = '/usr/local/sounds/samples'
#sampledir = '/kgb/c_out/sounds/samples'
tmpdir = '/tmp'

r2d2path = '/home/smile/projects/c_out/r2d2_wav'
txt2phopath = "/var/www/c_out.c-base.org/txt2speech/txt2pho"

acapelapassword = '0g7znor2aa'

logfile = '/home/smile/c_out.log'
