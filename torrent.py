
import argparse
import requests
import socket
import tparser
import hashlib
import reactor
import peer
import time
import os
import random
import json
import bencode

from string import ascii_letters, digits
from listener import Listener
from switchboard import Switchboard
VERSION = '0001'
ALPHANUM = ascii_letters + digits
DEFAULT_PORT = 55308
DEFAULT_DIR = '~/Desktop'


def connect_vis(address):
    ip, port = address.split(':')
    vis_addr_tuple = (ip, int(port))
    mysock = socket.socket()
    mysock.connect(vis_addr_tuple)
    return mysock


def get_path(file_path):
    if file_path[0] == '.':
        return os.path.abspath(file_path)
    elif file_path[0] == '~':
        return os.path.expanduser(file_path)
    else:
        return file_path


class PeerListener(Listener):
    def __init__(self, address='127.0.0.1', port=7000, torrent=None):
        Listener.__init__(self, address, port)
        self.torrent = torrent

    def read(self):
        newsock, _ = self.sock.accept()
        self.torrent.add_peer(newsock)




class Torrent(object):

    def __init__(self, torrent_path, directory='', port=55308,
                 download_all=False):
        torrent_dict = bencode.bdecode(bytes(open(torrent_path).read()))
        self.torrent_dict = torrent_dict
        self.peer_dict = {}
        self.peer_ips = []
        self.port = port
        self.download_all = download_all
        self.r = None
        self.tracker_response = None
        self.peer_dict = {}
        self.hash_string = None
        self.queued_requests = []
        self.reactor = reactor.Reactor()
        self.reactor.add_listeners([PeerListener(torrent=self, port=7000)])

        if directory:
            os.chdir(directory)
        if 'files' in self.torrent_dict['info']:
            dirname = self.torrent_dict['info']['name']
        else:
            dirname = None
        file_list = []

        if 'files' in self.torrent_dict['info']:
            file_list.extend(self.torrent_dict['info']['files'])
            multifile = True

        elif 'name' in self.torrent_dict['info']:
            info_dict = {}
            info_dict['path'] = self.torrent_dict['info']['name']
            info_dict['length'] = self.torrent_dict['info']['length']
            file_list.append(info_dict)
            multifile = False
        else:
            raise Exception('Invalid .torrent file')

        self.switchboard = Switchboard(dirname=dirname,
                                       file_list=file_list, piece_length=
                                       self.piece_length, num_pieces=
                                       self.num_pieces, multifile=multifile,
                                       download_all=download_all)

    @property
    def piece_length(self):
        return self.torrent_dict['info']['piece length']

    @property
    def num_pieces(self):
        num, rem = divmod(len(self.torrent_dict['info']['pieces']), 20)
        if rem == 0:
            return num
        else:
            raise Exception("Improperly formed 'pieces' entry in torrent_dict")

    @property
    def length(self):
        if 'files' in self.torrent_dict['info']:
            return sum([i['length'] for i in
                       self.torrent_dict['info']['files']])
        else:
            return self.torrent_dict['info']['length']

    @property
    def last_piece_length(self):
        return self.length - (self.piece_length * (self.num_pieces - 1))

    @property
    def last_piece(self):
        return self.num_pieces - 1

    def build_payload(self):
        payload = {}
        hashed_info = hashlib.sha1(tparser.bencode(self.torrent_dict['info']))
        self.hash_string = hashed_info.digest()
        self.peer_id = ('-DR' + VERSION +
                        ''.join(random.sample(ALPHANUM, 13)))
        assert len(self.peer_id) == 20
        payload['info_hash'] = self.hash_string
        payload['peer_id'] = self.peer_id
        payload['port'] = self.port
        payload['uploaded'] = 0
        payload['downloaded'] = 0
        payload['left'] = self.length
        payload['compact'] = 1
        payload['supportcrypto'] = 1
        payload['event'] = 'started'
        return payload

    def tracker_request(self):

        assert self.torrent_dict['info']
        payload = self.build_payload()

        self.r = requests.get(self.torrent_dict['announce'],
                                 params=payload)

        self.tracker_response = tparser.bdecode(self.r.content)
        self.get_peer_ips()

    def get_peer_ips(self):
        presponse = [ord(i) for i in self.tracker_response['peers']]
        while presponse:
            peer_ip = (('.'.join(str(x) for x in presponse[0:4]),
                       256 * presponse[4] + presponse[5]))
            if peer_ip not in self.peer_ips:
                self.peer_ips.append(peer_ip)
            presponse = presponse[6:]

    def handshake_peers(self):

        pstr = 'BitTorrent protocol'
        pstrlen = len(pstr)
        info_hash = self.hash_string
        peer_id = self.peer_id

        packet = ''.join([chr(pstrlen), pstr, chr(0) * 8, info_hash,
                          peer_id])
        print("Here's my packet {}").format(repr(packet))
        for i in self.peer_ips:
            if len(self.peer_dict) >= 30:
                break
            s = socket.socket()
            s.setblocking(True)
            s.settimeout(0.5)
            try:
                s.connect(i)
            except socket.timeout:
                print('Connecting...')
                continue
            except socket.error:
                print(' threw a socket error')
                continue
            except:
                raise Exception
            s.send(packet)
            try:
                data = s.recv(68)
                if data:
                    self.initpeer(s)
            except:
                continue
        else:
            self.peer_ips = []

    def initpeer(self, sock):
        location_json = requests.request("GET", "http://freegeoip.net/json/" + sock.getpeername()[0]).content
        location = json.loads(location_json)
        tpeer = peer.Peer(sock, self.reactor, self, location)
        self.peer_dict[sock] = tpeer
        self.reactor.select_list.append(tpeer)

    def add_peer(self, sock):
        print('adding peer at'), sock.getpeername()
        time.sleep(3)

    def kill_peer(self, tpeer):
        thispeer = self.peer_dict.pop(tpeer.sock)
        print('peer with fileno {} killing itself').format(thispeer.fileno())
        self.reactor.select_list.remove(thispeer)

    def set_sock(self, sock):
        self.vis_write_sock = sock
        self.switchboard.vis_write_sock = self.vis_write_sock

    def __enter__(self):
        pass

    def __exit__(self, type, value, tb):
        self.switchboard.close()


def main(path,dir):
    torrent_path = '/home/meliodas/451005/17.torrent'
    directory = '/home'
    torrent_path=path
    directory=dir
    mytorrent = Torrent(torrent_path, directory=directory)
    with mytorrent:
        mytorrent.tracker_request()
        mytorrent.handshake_peers()
        mytorrent.reactor.event_loop()


def open_socket(url):
    split_url = url.split(':')
    split_url[1] = int(split_url[1])
    split_url_tuple = tuple(split_url)
    mysock = socket.create_connection(split_url_tuple, 2)
    mysock.close()
    return url


if __name__ == '__main__':
    main()
