import os
import bitarray
import copy
import json
from collections import namedtuple


start_end_pair = namedtuple('start_end_pair', 'start end')


def all_subdirs(dir):
    subdirs = []
    dir_walker = os.walk(os.getcwd())
    while 1:
        try:
            subdirs.append(dir_walker.next()[0])
        except:
            return subdirs


def build_dirs(files):
    for i in files:
        if type(i) is list:
            build_dirs(i)
            continue
        else:
            if len(i['path']) > 1:
                addpath = os.path.join(os.getcwd(), *i['path'][:-1])
                subdirs = all_subdirs(os.getcwd())
                if addpath and addpath not in subdirs:
                    os.makedirs(addpath)
                    print( 'just made path', addpath)


def get_want_file_pos(file_list):
    want_file_pos = []
    print ('\nFiles contained:\n')
    for i in file_list:
        print(os.path.join(*i['path']))
    while 1:
        all_answer = 'y'
        if all_answer in ('y', 'n'):
            break
    if all_answer == 'y':
        want_file_pos = range(len(file_list))
        return want_file_pos
    if all_answer == 'n':
        for j, tfile in enumerate(file_list):
            while 1:
                file_answer = input('Do you want {}? '
                                        '(y/n): '.format(os.path.join
                                                        (*tfile['path'])))

                if file_answer in ('y', 'n'):
                    break
            if file_answer == 'y':
                want_file_pos.append(j)
        print ("Here are all the files you want:")
        for k in want_file_pos:
            print (os.path.join(*file_list[k]['path']))
        return want_file_pos


def get_file_starts(file_list):
    starts = []
    total = 0
    for i in file_list:
        starts.append(total)
        total += i['length']
    print( starts)
    return starts


def get_rightmost_index(byte_index=0, file_starts=[0]):

    i = 1
    while i <= len(file_starts):
        start = file_starts[-i]
        if start <= byte_index:
            return len(file_starts) - i
        else:
            i += 1
    else:
        raise Exception('byte_index lower than all file_starts')


def get_heads_tails(want_file_pos=[], file_starts=[], num_pieces=0,
                    piece_length=0):
    heads_tails = []
    for i in want_file_pos:
        head_tail = get_head_tail(want_index=i, file_starts=file_starts,
                                  num_pieces=num_pieces,
                                  piece_length=piece_length)
        heads_tails.append(head_tail)
    return heads_tails


def get_head_tail(want_index=0, file_starts=[], num_pieces=0,
                  piece_length=0):

    byte_start = file_starts[want_index]

    first_piece = byte_start // piece_length

    piece_pos = first_piece

    if want_index == len(file_starts) - 1:
        last_piece = num_pieces - 1

    elif want_index < len(file_starts) - 1:
        next_file_start = file_starts[want_index + 1]
        while piece_pos * piece_length < next_file_start:
            piece_pos += 1

        last_piece = piece_pos - 1

    return start_end_pair(start=first_piece, end=last_piece)


def get_write_index(write_file_description, outfiles):
    i = 0
    while i < len(outfiles):
        if outfiles[i].name == os.path.join(*write_file_description['path']):
            return i
        else:
            i += 1
    else:
        raise Exception('Nothing matches')


def build_bitfield(heads_and_tails=[], num_pieces=0):
    this_bitfield = bitarray.bitarray('0' * num_pieces)
    for i in heads_and_tails:
        for j in range(i.start, i.end + 1):
            this_bitfield[j] = True
    return this_bitfield


class Switchboard(object):
    def __init__(self, dirname='', file_list=[], piece_length=0, num_pieces=0,
                 multifile=False, download_all=False):
        self.dirname = dirname
        self.file_list = copy.deepcopy(file_list)
        self.piece_length = piece_length
        self.num_pieces = num_pieces
        self.file_starts = (get_file_starts(self.file_list) if multifile
                            else [0])

        self.download_all = download_all
        self.encoder = json.JSONEncoder()

        if self.download_all:
            self.want_file_pos = range(len(self.file_list))
        elif multifile:
            self.want_file_pos = (get_want_file_pos(self.file_list))
        else:
            self.want_file_pos = [0]

        self.outfiles = []
        self.queued_messages = []
        if self.dirname:
            if not os.path.exists(self.dirname):
                os.mkdir(self.dirname)
            os.chdir(os.path.join(os.getcwd(), self.dirname))
        want_files = [self.file_list[index] for index in self.want_file_pos]
        if multifile:
            build_dirs(want_files)
        for i in self.want_file_pos:
            if multifile:
                thisfile = open(os.path.join(*self.file_list[i]
                                             ['path']), 'w')
            else:
                thisfile = open(self.file_list[i]['path'], 'w')
            self.outfiles.append(thisfile)
        self.heads_and_tails = get_heads_tails(want_file_pos=
                                               self.want_file_pos,
                                               file_starts=self.file_starts,
                                               num_pieces=self.num_pieces,
                                               piece_length=self.piece_length)
        self.bitfield = build_bitfield(self.heads_and_tails,
                                       num_pieces=self.num_pieces)
        self.vis_init()

    def get_next_want_file(self, byte_index, block):
        while block:
            rightmost = get_rightmost_index(byte_index=byte_index,
                                            file_starts=self.file_starts)
            if rightmost in self.want_file_pos:
                return rightmost, byte_index, block
            else:
                    file_start = (self.file_starts
                                  [rightmost])
                    file_length = self.file_list[rightmost]['length']
                    bytes_rem = file_start + file_length - byte_index
                    if len(block) > bytes_rem:
                        block = block[bytes_rem:]
                        byte_index = byte_index + bytes_rem
                    else:
                        block = ''
        else:
            return None

    def set_piece_index(self, piece_index):
        self.piece_index = piece_index

    def write(self, byte_index, block):

        try:
            a = self.get_next_want_file(byte_index, block)
            file_list_index, write_byte_index, block = a
        except:
            return

        if (file_list_index is not None and write_byte_index is not None and
                block is not ''):
            index_in_want_files = self.want_file_pos.index(file_list_index)
            write_file = self.outfiles[index_in_want_files]
            file_start = self.file_starts[file_list_index]
            file_internal_index = write_byte_index - file_start
            if write_file.closed:
                return
            write_file.seek(file_internal_index)
            file_length = self.file_list[file_list_index]['length']
            bytes_writable = file_length - file_internal_index
            if bytes_writable < len(block):
                write_file.write(block[:bytes_writable])
                block = block[bytes_writable:]
                write_byte_index = write_byte_index + bytes_writable
                j = self.file_starts.index(file_start) + 1
                if j <= self.want_file_pos[-1]:
                    self.write(write_byte_index, block)
                else:
                    return
            else:
                write_file.write(block)
                block = ''

    def vis_init(self):
        init_dict = {}
        init_dict['kind'] = 'init'
        assert len(self.want_file_pos) == len(self.heads_and_tails)
        init_dict['want_file_pos'] = self.want_file_pos
        init_dict['files'] = self.file_list
        init_dict['heads_and_tails'] = self.heads_and_tails
        init_dict['num_pieces'] = self.num_pieces
        self.broadcast(init_dict)

    def broadcast(self, data_dict):
        pass

    def send_all_updates(self):
        while self.queued_messages:
            next_message = (self.encoder.encode(self.queued_messages.pop(0)) +'\r\n\r\n')
            self.vis_socket.send(next_message)

    def mark_off(self, index):
        self.bitfield[index] = False

    @property
    def complete(self):
        if any(self.bitfield):
            return False
        else:
            return True

    def close(self):
        for i in self.outfiles:
            i.close()
