import sys
import torrent
from PyQt4 import QtGui, QtCore


class Myform(QtGui.QMainWindow):
    def someFunc(self):
        torrent_path = QtGui.QFileDialog.getOpenFileName(self, "Open Torrent File", '/home', "(*.torrent)")
        downland_path = QtGui.QFileDialog.getExistingDirectory(self, "Open Downland Dir", '/home')
        torrent.main(torrent_path, downland_path)

    def __init__(self, parent=None):
        QtGui.QMainWindow.__init__(self)

        self.setGeometry(300, 300, 1200, 450)
        self.setWindowTitle('MyTorrent')
        self.textEdit = QtGui.QTextEdit("",self)
        self.textEdit.setGeometry(40, 40, 1120, 300)

        self.open = QtGui.QPushButton('Open Torrent File', self)
        self.open.setGeometry(500, 350, 160, 35)
        self.statusBar().showMessage('Ready')
        self.connect(self.open, QtCore.SIGNAL('clicked()'), self.someFunc)
        self.center()



    def center(self):
        screen = QtGui.QDesktopWidget().screenGeometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) / 2, (screen.height() - size.height()) / 2)


    def closeEvent(self, event):
        reply = QtGui.QMessageBox.question(self, 'Message',"Are you sure to quit?", QtGui.QMessageBox.No, QtGui.QMessageBox.Yes)

        if reply == QtGui.QMessageBox.Yes:
            event.accept()
        else:
            event.accept()

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    mf = Myform()
    mf.show()
    sys.exit(app.exec_())