import json
import socket
import struct
import sys
from queue import Queue

from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


HOST = "127.0.0.1"
PORT = 50505


class NetCom:
    def __init__(self, sock):
        self.sock = sock

    @staticmethod
    def _recv_exact(sock, size):
        chunks = []
        received = 0
        while received < size:
            chunk = sock.recv(size - received)
            if not chunk:
                return None
            chunks.append(chunk)
            received += len(chunk)
        return b"".join(chunks)

    def recv(self):
        header = self._recv_exact(self.sock, 4)
        if header is None:
            return None

        payload_size = struct.unpack("!I", header)[0]
        payload = self._recv_exact(self.sock, payload_size)
        if payload is None:
            return None

        return json.loads(payload.decode("utf-8"))

    def send(self, message):
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = struct.pack("!I", len(payload))
        self.sock.sendall(header + payload)


class ReceiveThread(QThread):
    message_received = pyqtSignal(dict)
    connection_lost = pyqtSignal()

    def __init__(self, net):
        super().__init__()
        self.net = net

    def run(self):
        while True:
            try:
                message = self.net.recv()
            except (ConnectionError, OSError):
                message = None

            if message is None:
                self.connection_lost.emit()
                break

            self.message_received.emit(message)


class SendThread(QThread):
    def __init__(self, net):
        super().__init__()
        self.net = net
        self.queue = Queue()

    def send(self, message):
        self.queue.put(message)

    def stop(self):
        self.queue.put(None)

    def run(self):
        while True:
            message = self.queue.get()
            if message is None:
                break

            try:
                self.net.send(message)
            except (ConnectionError, OSError):
                break


class MainWindow(QMainWindow):
    def __init__(self, net, sock):
        super().__init__()
        self.net = net
        self.sock = sock

        self.setWindowTitle("PyQt6 network chat")
        self.resize(560, 460)

        self.status_label = QLabel("Connected")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Введите ваше имя…")
        self.username_input.setText("Аноним")

        user_row = QHBoxLayout()
        user_row.addWidget(QLabel("Имя:"))
        user_row.addWidget(self.username_input)

        self.history = QTextEdit()
        self.history.setReadOnly(True)

        self.clear_button = QPushButton("Clear history")
        self.clear_button.clicked.connect(self.on_clear_clicked)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a message…")

        self.send_button = QPushButton("Send")

        input_row = QHBoxLayout()
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addLayout(user_row)
        layout.addWidget(self.history)
        layout.addWidget(self.clear_button)
        layout.addLayout(input_row)

        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

        self.send_button.clicked.connect(self.on_send_clicked)
        self.input.returnPressed.connect(self.on_send_clicked)

        self.receive_thread = ReceiveThread(self.net)
        self.receive_thread.message_received.connect(self.handle_message)
        self.receive_thread.connection_lost.connect(self.on_connection_lost)
        self.receive_thread.start()


        self.send_thread = SendThread(self.net)
        self.send_thread.start()

    def on_send_clicked(self):
        text = self.input.text()
        if not text.strip():
            return

        username = self.username_input.text().strip() or "Аноним"

        self.send_thread.send({
            "type": "chat",
            "username": username,
            "text": text.strip(),
        })

        self.input.clear()

    def on_clear_clicked(self):
        self.history.clear()

    def handle_message(self, message):
        msg_type = message.get("type")
        if msg_type == "chat":
            username = message.get("username", "Неизвестный")
            text = message.get("text", "")
            self.history.append(f"{username}: {text}")
        elif msg_type == "system":
            text = message.get("text", "")
            self.history.append(f"[Система] {text}")

    def on_connection_lost(self):
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self.history.append("[Система] Соединение с сервером потеряно.")
        self.input.setEnabled(False)
        self.send_button.setEnabled(False)

    def closeEvent(self, event):
        self.send_thread.stop()

        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

        self.send_thread.wait(1000)
        self.receive_thread.wait(1000)

        event.accept()


def main():
    app = QApplication(sys.argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except OSError as exc:
        print(f"Could not connect to server at {HOST}:{PORT}: {exc}")
        print("Run server.py first, then start main.py.")
        return

    net = NetCom(sock)
    window = MainWindow(net, sock)
    window.show()

    exit_code = app.exec()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
