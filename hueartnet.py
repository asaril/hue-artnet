# SPDX-License-Identifier: MIT
# Copyright (c) 2021, Patrick Moessler

from random import uniform
import json
import requests
import sys
import struct
from time import sleep, time
from socket import socket, AF_INET, SOCK_DGRAM, timeout
from mbedtls import tls, exceptions

if sys.platform == "Windows":
    import ctypes
    winmm = ctypes.WinDLL('winmm')
    winmm.timeBeginPeriod(1)


class HueEntertainment:
    def __init__(self, ip, username, key, group_name=None, mapping=None):
        self.ip = ip
        self.username = username
        self.group = self.get_group_id(group_name) if group_name else None
        self.mapping = {}
        if mapping:
            for mp in mapping:
                self.mapping[mp["light"]] = (mp["start"]-1, mp.get("fine", False))  # start in dmx is from 1
        self.sock = None

        self.dtls_cli_ctx = tls.ClientContext(tls.DTLSConfiguration(
            pre_shared_key=(username, bytes.fromhex(key)),
            ciphers=[
                # 'TLS-PSK-WITH-AES-128-CBC-SHA',
                # 'TLS-PSK-WITH-AES-128-CBC-SHA256',
                # 'TLS-PSK-WITH-AES-128-CCM-8',
                # 'TLS-PSK-WITH-AES-128-CCM',
                # 'TLS-PSK-WITH-AES-128-GCM-SHA256',
                # 'TLS-PSK-WITH-AES-256-CBC-SHA',
                # 'TLS-PSK-WITH-AES-256-CBC-SHA384',
                # 'TLS-PSK-WITH-AES-256-CCM-8',
                # 'TLS-PSK-WITH-AES-256-CCM',
                'TLS-PSK-WITH-AES-256-GCM-SHA384'
            ]
        ))
        # tls._set_debug_level(2)
        # tls._enable_debug_output(self.dtls_cli_ctx.configuration)

    def _user_get(self, api, data=None):
        return requests.get(f'http://{self.ip}/api/{self.username}/{api}', json=data).json()

    def _user_post(self, api, data):
        return requests.post(f'http://{self.ip}/api/{self.username}/{api}', json=data).json()

    def _user_put(self, api, data):
        return requests.put(f'http://{self.ip}/api/{self.username}/{api}', json=data).json()

    def list_entertainment_groups(self):
        all_groups = self._user_get('groups')
        return {id: all_groups[id] for id in all_groups if all_groups[id]["type"] == "Entertainment"}

    def print_entertainment_groups(self):
        from pprint import pprint as pp
        eg = self.list_entertainment_groups()
        pp(eg)

    def get_group_id(self, name):
        eg = self.list_entertainment_groups()
        return [grp for grp in eg if eg[grp]["name"] == name][0]

    def identify_lights(self):
        lights = self._user_get(f'groups/{self.group}')["lights"]
        for light in sorted(lights):
            print(f'\nLight #{light}')
            req_data = {"alert": "lselect"}
            self._user_put(f'lights/{light}/state', req_data)
            sleep(3)
            req_data = {"alert": "none"}
            self._user_put(f'lights/{light}/state', req_data)
            sleep(1)

    # def set_light(self, id, r, g, b):
    #     rgb = sRGBColor(r, g, b, True)
    #     xyY = convert_color(rgb, xyYColor, target_illuminant="d65")
    #     req_data = {"xy": [xyY.xyy_x, xyY.xyy_y], "bri": int(xyY.xyy_Y * 254)}
    #     print(req_data)
    #     self._user_put(f'lights/{id}/state', req_data)

    def connect_stream(self):
        req_data = {"stream": {"active": True}}
        r = self._user_put(f'groups/{self.group}', req_data)[0]
        if "success" in r:
            s = socket(AF_INET, SOCK_DGRAM)
            self.sock = self.dtls_cli_ctx.wrap_socket(s, None)
            self.sock.connect((self.ip, 2100))
        else:
            print(r)

    def disconnect_stream(self):
        if self.sock:
            self.sock.close()
        req_data = {"stream": {"active": False}}
        self._user_put(f'groups/{self.group}', req_data)

    def send_state(self, states):
        count = len(states)
        light_data = bytearray([0]*(16+count*9))
        struct.pack_into(">9s2BB2BBB", light_data, 0,
                         "HueStream".encode('ascii'),  # Protocol Name (fixed)
                         0x01, 0x00,                   # Version (=01.00)
                         0x00,                         # Sequence Id (ignored)
                         0x00, 0x00,                   # Reserved (zeros)
                         0x00,                         # Color Space (RGB=0)
                         0x00                          # Reserved (zero)
                         )
        for i in range(count):
            struct.pack_into(">BHHHH", light_data, 16 + i*9,
                             0x00,  # Type: Light
                             states[i][0],
                             states[i][1],
                             states[i][2],
                             states[i][3]
                             )
        if self.sock:
            self.sock.send(light_data)

    def handle_dmx(self, dmx):
        states = []
        for light, (start, fine) in self.mapping.items():
            if fine:
                if start+5 < len(dmx):
                    r = dmx[start+0]*256 + dmx[start+1]
                    g = dmx[start+2]*256 + dmx[start+3]
                    b = dmx[start+4]*256 + dmx[start+5]
            else:
                if start+2 < len(dmx):
                    r = dmx[start+0]*256
                    g = dmx[start+1]*256
                    b = dmx[start+2]*256
            states.append((light, r, g, b))
        print(states)
        if states:
            self.send_state(states)


class ArtNetReceiver:
    MAGIC = 'Art-Net\0'.encode('ascii')

    def __init__(self, ip, port, universe):
        self.universe = universe
        self.sock = socket(AF_INET, SOCK_DGRAM)
        self.sock.bind((ip, port))
        self.sock.settimeout(10)
        self.seq = 0

    def shutdown(self):
        if self.sock:
            self.sock.close()

    def recv_loop(self, handler):
        active = False
        try:
            while self.sock:
                msg = None
                try:
                    msg = self.sock.recv(530)
                except timeout:
                    if active:
                        break
                if not msg:
                    break

                active = True
                if len(msg) < 18:
                    continue
                if(msg[0:8] != ArtNetReceiver.MAGIC):
                    continue
                data = self.handle(msg)
                if data:
                    handler(data)
        except KeyboardInterrupt:
            pass  # just leave here and shut down

    def handle(self, msg):
        hdr = struct.unpack(">HHBBHH", msg[8:18])
        if hdr[0] != 0x0050:  # byteswapped!
            return
        if hdr[1] != 14:
            return
        if hdr[2] != 0 and hdr[2] < self.seq and (self.seq - hdr[2]) < 10:
            return
        if hdr[4] != self.universe:
            return
        if len(msg) < 18+hdr[5]:
            return
        data = msg[18:18+hdr[5]]
        # print(msg[0:48].hex())
        return data


# MAIN
cfg = None
with open('config.json') as cfg_file:
    cfg = json.load(cfg_file)

# no config
if not cfg:
    print('please create config.json')
    sys.exit(-1)

# no group
if not "group" in cfg["hue"]:
    h = HueEntertainment(cfg["hue"]["ip"], cfg["hue"]["username"], cfg["hue"]["clientkey"])
    h.print_entertainment_groups()
    print('please add group name to config.json')
    sys.exit(-1)

if not "mapping" in cfg:
    h = HueEntertainment(cfg["hue"]["ip"], cfg["hue"]["username"], cfg["hue"]["clientkey"], cfg["hue"]["group"])
    h.identify_lights()
    sys.exit(-1)

# all fine, can connect
h = HueEntertainment(cfg["hue"]["ip"], cfg["hue"]["username"], cfg["hue"]
                 ["clientkey"], cfg["hue"]["group"], cfg["mapping"])

h.connect_stream()

connected = False
for _ in range(10):
    try:
        sleep(0.2)
        h.sock.do_handshake()
        connected = True
    except exceptions.TLSError as e:
        print(f"###########+#{str(e)}#+#############")

h.send_state([(31, 0, 0, 0)])
sleep(0.1)
h.send_state([(31, 255, 0, 0)])
sleep(0.1)
h.send_state([(31, 0, 255, 0)])
sleep(0.1)
h.send_state([(31, 0, 0, 255)])
sleep(0.1)
h.send_state([(31, 0, 0, 0)])
sleep(0.1)

a = ArtNetReceiver(cfg["art-net"]["ip"], cfg["art-net"]["port"], cfg["art-net"]["universe"])
a.recv_loop(h.handle_dmx)

print("art-net lost, shutting down")

h.disconnect_stream()
