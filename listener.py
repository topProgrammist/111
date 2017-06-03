import socket
from abc import abstractmethod, ABCMeta


class Listener(object):

    __metaclass__ = ABCMeta

    def __init__(self, address='127.0.0.1', port=7000):
        self.socky = socket.socket()
        self.socky.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socky.bind((address, port))
        self.socky.listen(5)
        print('listening on {}:{}'.format(address, port))

    @abstractmethod
    def read(self):
        pass

    def fileno(self):
        return self.socky.fileno()

    def write(self):
        pass
