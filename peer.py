from bitarray import bitarray
from piece import Piece
import struct
import random
import hashlib
from math import ceil
from  mainform import Myform

REQUEST_SIZE = 2 ** 14


class Peer(object):
    def __init__(self, sock, reactor, torrent, in_location):
        self.sock = sock
        self.sock.setblocking(True)
        self.reactor = reactor
        self.torrent = torrent
        loc_list = ['city', 'region_name', 'country_name']
        self.location = {key: in_location[key] for key in loc_list if key in in_location and in_location[key]}

        self.valid_indices = []
        self.bitfield = None
        self.max_size = 16 * 1024
        self.states = {'reading_length': 0, 'reading_id': 1, 'reading_message': 2}
        self.save_state = {'state': self.states['reading_length'], 'length': 0, 'message_id': None, 'message': '', 'remainder': ''}
        self.message_codes = ['choke', 'unchoke', 'interested', 'not interested', 'have', 'bitfield', 'request', 'piece', 'cancel', 'port']
        self.ischoking = True
        self.isinterested = False
        self.unchoke()
        activate_dict = {'kind': 'activate', 'address': self.getpeername(), 'location': self.location}
        self.torrent.switchboard.broadcast(activate_dict)

    def fileno(self):
        return self.sock.fileno()

    def getpeername(self):
        return self.sock.getpeername()

    def read(self):
        try:
            bytes = self.sock.recv(self.max_size)
        except:
            self.torrent.kill_peer(self)
            return
        if len(bytes) == 0:
            print ('Got 0 bytes from fileno {}.'.format(self.fileno()))
            self.torrent.kill_peer(self)
        self.process_input(bytes)

    def process_input(self, bytes):
        while bytes:
            if self.save_state['state'] == self.states['reading_length']:
                bytes = self.get_message_length(bytes)
            elif self.save_state['state'] == self.states['reading_id']:
                bytes = self.get_message_id(bytes)
            elif self.save_state['state'] == self.states['reading_message']:
                bytes = self.get_message(bytes)

    def get_message_length(self, instr):

            if self.save_state['remainder']:
                instr = self.save_state['remainder'] + instr
                self.save_state['remainder'] = ''

            if len(instr) >= 4:

                self.save_state['length'] = struct.unpack('!i', instr[0:4])[0]
                if self.save_state['length'] == 0:
                    self.keep_alive()
                    self.save_state['state'] = self.states['reading_length']
                    return instr[4:]
                else:
                    self.save_state['state'] = self.states['reading_id']
                    return instr[4:]

            else:
                self.save_state['remainder'] = instr
                return ''

    def get_message_id(self, instr):
        self.save_state['message_id'] = struct.unpack('b', instr[0])[0]
        self.save_state['state'] = self.states['reading_message']
        return instr[1:]

    def get_message(self, instr):
        length_after_id = self.save_state['length'] - 1
        if length_after_id == 0:
            self.save_state['state'] = self.states['reading_length']
            self.save_state['message_id'] = None
            self.save_state['message'] = ''
            return instr

        if self.save_state['remainder']:
            instr = self.save_state['remainder'] + instr

        if len(instr) >= length_after_id:

            self.save_state['message'] = instr[:length_after_id]

            self.handle_message()
            self.reset_state()
            return instr[length_after_id:]

        else:
            self.save_state['remainder'] = instr
            return None

    def reset_state(self):
        self.save_state['state'] = self.states['reading_length']
        self.save_state['length'] = 0
        self.save_state['message_id'] = None
        self.save_state['message'] = ''
        self.save_state['remainder'] = ''

    def handle_message(self):
        if self.save_state['message_id'] == 0:
            self.pchoke()
        elif self.save_state['message_id'] == 1:
            self.punchoke()
        elif self.save_state['message_id'] == 2:
            self.pinterested()
        elif self.save_state['message_id'] == 3:
            self.pnotinterested()
        elif self.save_state['message_id'] == 4:
            self.phave()
        elif self.save_state['message_id'] == 5:
            self.pbitfield()
        elif self.save_state['message_id'] == 6:
            self.prequest()
        elif self.save_state['message_id'] == 7:
            self.ppiece(self.save_state['message'])
        elif self.save_state['message_id'] == 8:
            self.pcancel()
        elif self.save_state['message_id'] == 9:
            pass

    def pchoke(self):
        print ('choke')
        self.ischoking = True

    def punchoke(self):
        print ('unchoke')
        self.ischoking = False

    def pinterested(self):
        print ('pinterested')

    def pnotinterested(self):
        print ('pnotinterested')

    def phave(self):
        index = struct.unpack('>i', self.save_state['message'])[0]
        self.bitfield[index] = True

    def pbitfield(self):
        self.bitfield = bitarray()
        self.bitfield.frombytes(self.save_state['message'])
        self.interested()
        self.unchoke()
        self.piece = self.init_piece()
        self.request_all()

    def prequest(self):
        print ('prequest')

    def ppiece(self, content):
        piece_index, byte_begin = struct.unpack('!ii', content[0:8])

        if piece_index != self.piece.index:
            return

        assert byte_begin % REQUEST_SIZE == 0
        block_begin = byte_begin / REQUEST_SIZE
        block = content[8:]
        self.piece.save(index=block_begin, bytes=block)
        if self.piece.complete:
            piece_bytes = self.piece.get_bytes()
            if self.piece.index == self.torrent.last_piece:
                piece_bytes = piece_bytes[:self.torrent.last_piece_length]
            if hashlib.sha1(piece_bytes).digest() == (self.torrent.torrent_dict['info']['pieces'][20 * piece_index:20 * piece_index + 20]):
                piece_dict = {'kind': 'piece', 'peer': self.sock.getpeername(),
                              'piece_index': piece_index}
                self.torrent.switchboard.broadcast(piece_dict)

                print ('writing piece {}. Length is {}').format(repr(piece_bytes)[:10] + '...', len(piece_bytes))

                byte_index = piece_index * self.torrent.piece_length
                self.piece = self.init_piece()
                self.request_all()
                self.torrent.switchboard.write(byte_index, piece_bytes)
                self.torrent.switchboard.mark_off(piece_index)
                print (self.torrent.switchboard.bitfield)
                if self.torrent.switchboard.complete:
                    print ('\nDownload complete\n')
                    self.reactor.is_running = False
            else:
                print ("Bad data -- hash doesn't match. Discarding piece.")
                self.piece = self.init_piece()
                self.request_all()

    def pcancel(self):
        print ('pcancel')

    def read_timeout(self):
        print ('Timeout on read attempt. Re-requesting piece.')
        self.request_all()

    def interested(self):
        packet = ''.join(struct.pack('!ib', 1, 2))
        self.sock.send(packet)

    def unchoke(self):
        packet = struct.pack('!ib', 1, 1)
        self.sock.send(packet)

    def keep_alive(self):
        print( 'keep_alive')

    def write(self):
        pass

    def get_piece_length(self, index):
        if index == self.torrent.last_piece:
            return self.torrent.last_piece_length
        else:
            return self.torrent.piece_length

    def init_piece(self):
        valid_indices = []
        for i in range(self.torrent.num_pieces):
            assert self.bitfield
            if (self.torrent.switchboard.bitfield[i] is True
                    and self.bitfield[i] is True):
                valid_indices.append(i)
        if not valid_indices:
            return
        else:
            index = random.choice(valid_indices)
        length = self.get_piece_length(index)
        if index is self.torrent.last_piece:
            num_blocks = int(ceil(float(length) / REQUEST_SIZE))
        else:
            num_blocks = int(ceil(float(length) / REQUEST_SIZE))
        return Piece(index=index, num_blocks=num_blocks,request_size=REQUEST_SIZE)

    def request_all(self):
        if not self.piece:
            return
        for i in range(self.piece.num_blocks):
            self.request_block(i)
        request_dict = {'kind': 'request',
                        'peer': self.sock.getpeername(), 'piece': self.piece.index}
        self.torrent.switchboard.broadcast(request_dict)
        print ('next request:', request_dict)

    def get_last_block_size(self):
        return self.torrent.last_piece_length % REQUEST_SIZE

    def request_block(self, block_index):
        byte_index = block_index * REQUEST_SIZE
        if (self.piece.index == self.torrent.last_piece and
                byte_index == self.piece.last_block):
            request_size = self.get_last_block_size()
        else:
            request_size = REQUEST_SIZE
        packet = ''.join(struct.pack('!ibiii', 13, 6, self.piece.index, byte_index, request_size))
        bytes = self.sock.send(packet)
        if bytes != len(packet):
            raise Exception('couldnt send request')
