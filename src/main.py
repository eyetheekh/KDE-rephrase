import json
import os
import sys

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    Qt,
    pyqtClassInfo,
    pyqtProperty,
    pyqtSlot,
)
from PyQt6.QtDBus import QDBusAbstractAdaptor, QDBusConnection
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QKeySequence, QShortcut
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chat import ChatClient

# ---- palette -----------------------------------------------------------
BG = "#15161C"
SURFACE = "#1B1D25"
FIELD = "#20222C"
FIELD_FOCUS = "#262838"
BORDER = "#2C2F3D"
BORDER_FOCUS = "#8B7FE8"
TEXT = "#E7E7EE"
TEXT_DIM = "#787C8F"
ACCENT = "#8B7FE8"
ACCENT_SOFT = "#4B4570"
ERROR = "#E5707E"
SUCCESS = "#6FCF9E"

STATE_COLORS = {
    "idle": BORDER,
    "loading": ACCENT,
    "success": SUCCESS,
    "error": ERROR,
}


class StateRail(QWidget):
    """slim vertical bar on the window's leading edge that IS the status indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(4)
        self._color = QColor(STATE_COLORS["idle"])
        self._anim = QPropertyAnimation(self, b"railColor")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def getRailColor(self):
        return self._color

    def setRailColor(self, color):
        self._color = color
        self.setStyleSheet(f"background-color: {color.name()};")

    railColor = pyqtProperty(QColor, getRailColor, setRailColor)

    def set_state(self, state: str):
        self._anim.stop()
        self._anim.setStartValue(self._color)
        self._anim.setEndValue(QColor(STATE_COLORS[state]))
        self._anim.start()


@pyqtClassInfo("D-Bus Interface", "org.kde.rephraser.MainWindow")
class RephraserAdaptor(QDBusAbstractAdaptor):
    """Exports exactly one method on the session bus"""

    def __init__(self, window):
        super().__init__(window)
        self._window = window

    @pyqtSlot()
    def showHide(self):
        self._window.showHide()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.nam = QNetworkAccessManager(self)
        self.nam.finished.connect(self.on_request_finished)

        self._chat_client = ChatClient(
            base_url=os.getenv("BASE_URL"),
            api_key=os.getenv("API_KEY"),
            model_id=os.getenv("MODEL_ID"),
            system_instructions=os.getenv("SYSTEM_INSTRUCTIONS"),
        )

        # True once a response (success or error) is on screen. Drives two
        # things: typing resets to a fresh query, and Tab jumps to Copy.
        self._response_shown = False

        self.init_ui()

    # -- setup -------------------------------------------------------
    def _mono_font(self, size=13):
        families = QFontDatabase.families()
        for candidate in (
            "JetBrains Mono",
            "Cantarell",
            "Noto Sans Mono",
            "DejaVu Sans Mono",
        ):
            if candidate in families:
                return QFont(candidate, size)
        return QFont("monospace", size)

    def init_ui(self):
        self.setWindowTitle("Rephrase")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(620, 108)
        self.setMinimumWidth(620)

        central = QWidget(self)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.rail = StateRail(central)
        outer.addWidget(self.rail)

        card = QWidget(central)
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 18)
        card_layout.setSpacing(10)
        outer.addWidget(card, 1)

        self.setCentralWidget(central)

        # drop shadow so the frameless window reads as a floating palette,
        # not a flat rectangle pasted on the desktop
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)

        # eyebrow row: label + dismiss hint, sets tone without adding chrome
        eyebrow_row = QHBoxLayout()
        eyebrow_row.setSpacing(8)
        self.eyebrow = QLabel("REPHRASE")
        self.eyebrow.setObjectName("eyebrow")
        hint = QLabel("Esc to dismiss")
        hint.setObjectName("hint")
        eyebrow_row.addWidget(self.eyebrow)
        eyebrow_row.addStretch(1)
        eyebrow_row.addWidget(hint)
        card_layout.addLayout(eyebrow_row)

        self.textbox = QLineEdit()
        self.textbox.setObjectName("input")
        self.textbox.setPlaceholderText("Type text to rephrase, then press Enter…")
        self.textbox.setMaxLength(100000000)
        self.textbox.setFont(self._mono_font(14))
        self.textbox.returnPressed.connect(self.handle_enter)
        self.textbox.installEventFilter(self)
        card_layout.addWidget(self.textbox)

        # response area starts collapsed — the window itself grows when a
        # result arrives, rather than showing an empty box up front
        self.response = QTextEdit()
        self.response.setObjectName("response")
        self.response.setReadOnly(True)
        self.response.setFont(self._mono_font(13))
        self.response.setVisible(False)
        self.response.setFixedHeight(0)
        card_layout.addWidget(self.response)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        action_row.addWidget(self.status_label)
        action_row.addStretch(1)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.copy_btn.clicked.connect(self.copy_response)
        self.copy_btn.setVisible(False)
        action_row.addWidget(self.copy_btn)
        card_layout.addLayout(action_row)

        # NOTE: D-Bus integration is active — the app registers on the
        # session bus as org.kde.rephraser and exports showHide() at
        # /org/kde/rephraser via a dedicated adaptor (see
        # RephraserAdaptor), under the fixed interface
        # org.kde.rephraser.MainWindow.
        #
        # THIS is the actual global shortcut to be called.
        # e.g. via System Settings -> Shortcuts ->
        # Custom Shortcuts, running:
        #   qdbus6 org.kde.rephraser /org/kde/rephraser org.kde.rephraser.MainWindow.showHide
        #
        # The Alt+P QShortcut below is NOT a global hotkey — QShortcut
        # only fires while this window is the active/focused window, so
        # it's just a convenience toggle for when the window is already
        # open. It can never be what reopens a HIDDEN window; only the
        # D-Bus call above (triggered by a real KDE global shortcut) can.

        self.shortcut = QShortcut(QKeySequence("Alt+P"), self)
        self.shortcut.activated.connect(self.showHide)

        QShortcut(QKeySequence("Escape"), self, activated=self.hide)

        self.setStyleSheet(f"""
            #card {{
                background-color: {SURFACE};
                border-radius: 14px;
            }}
            #eyebrow {{
                color: {ACCENT};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
            }}
            #hint {{
                color: {TEXT_DIM};
                font-size: 11px;
            }}
            #input {{
                background-color: {FIELD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 9px;
                padding: 11px 14px;
            }}
            #input:focus {{
                background-color: {FIELD_FOCUS};
                border: 1px solid {BORDER_FOCUS};
            }}
            #response {{
                background-color: {FIELD};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 9px;
                padding: 12px 14px;
                selection-background-color: {ACCENT_SOFT};
            }}
            #status {{
                color: {TEXT_DIM};
                font-size: 12px;
            }}
            #copyBtn {{
                background-color: transparent;
                color: {ACCENT};
                border: 1px solid {ACCENT_SOFT};
                border-radius: 7px;
                padding: 5px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            #copyBtn:hover {{
                background-color: {ACCENT_SOFT};
            }}
            #copyBtn:pressed {{
                background-color: {ACCENT};
                color: {SURFACE};
            }}
            QWidget {{
                font-family: "Inter", "Cantarell", "Noto Sans", sans-serif;
            }}
        """)

        self.rail.set_state("idle")

    # -- behaviour -----------------------------------------------------
    def close_app(self):
        QApplication.instance().quit()

    @pyqtSlot()
    def showHide(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.textbox.setFocus(Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, obj, event):
        if obj is self.textbox and event.type() == QEvent.Type.KeyPress:
            key = event.key()

            # Tab jumps straight to Copy once a response is on screen,
            # instead of following the normal (empty) tab chain.
            if key == Qt.Key.Key_Tab and self.copy_btn.isVisible():
                self.copy_btn.setFocus(Qt.FocusReason.TabFocusReason)
                return True  # consumed — skip Qt's default tab handling

            # Any other real keypress after a response starts a clean
            # slate: clear the stale query/response, then let this
            # keypress carry on so typing isn't swallowed.
            modifier_only = key in (
                Qt.Key.Key_Shift,
                Qt.Key.Key_Control,
                Qt.Key.Key_Alt,
                Qt.Key.Key_Meta,
                Qt.Key.Key_AltGr,
                Qt.Key.Key_CapsLock,
            )
            if self._response_shown and key != Qt.Key.Key_Escape and not modifier_only:
                self._reset_for_new_query()

                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):  # noqa: SIM103
                    return True  # box is now empty — nothing to submit
                return False  # fall through so the character gets typed

        return super().eventFilter(obj, event)

    def _reset_for_new_query(self):
        self.textbox.clear()
        self.response.clear()
        self._expand_response(False)
        self.copy_btn.setVisible(False)
        self.status_label.setText("")
        self.rail.set_state("idle")
        self._response_shown = False

    def handle_enter(self):
        user_input = self.textbox.text().strip()
        if not user_input:
            return
        self.make_request(user_input)

    def copy_response(self):
        QApplication.clipboard().setText(self.response.toPlainText())
        self.status_label.setText("Copied to clipboard")

    def _expand_response(self, expand: bool):
        target = 180 if expand else 0
        self.response.setVisible(expand)
        self.response.setFixedHeight(target)
        # let the frameless top-level window resize to fit its content
        self.adjustSize()

    def make_request(self, text):
        self._response_shown = False
        self.rail.set_state("loading")
        self.status_label.setText("Fetching…")
        self.copy_btn.setVisible(False)
        self.textbox.setEnabled(False)

        request, byte_data = self._chat_client.send_request(text)
        self.nam.post(request, byte_data)

    def on_request_finished(self, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            response_bytes = reply.readAll()
            response_text = str(response_bytes, encoding="utf-8")
            try:
                response_json = json.loads(response_text)
                result = response_json["choices"][0]["message"]["content"]
                self.response.setPlainText(result)
                self._expand_response(True)
                self.copy_btn.setVisible(True)
                self.status_label.setText("Done")
                self.rail.set_state("success")
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                self.response.setPlainText(
                    f"Couldn't parse the response.\n\n{e}\n\n{response_text}"
                )
                self._expand_response(True)
                self.status_label.setText("Parse error")
                self.rail.set_state("error")
        else:
            self.response.setPlainText(f"{reply.errorString()}")
            self._expand_response(True)
            self.status_label.setText(f"Request failed ({reply.error()})")
            self.rail.set_state("error")

        reply.deleteLater()
        self._response_shown = True
        self.textbox.setEnabled(True)
        self.textbox.setFocus(Qt.FocusReason.OtherFocusReason)
        self.textbox.selectAll()


def _build_tray(window: "MainWindow") -> QSystemTrayIcon:
    icon = QIcon.fromTheme("edit-copy", QIcon.fromTheme("dialog-information"))
    tray = QSystemTrayIcon(icon, window)
    tray.setToolTip("Rephrase — running")

    menu = QMenu()
    show_action = menu.addAction("Show / Hide")
    show_action.triggered.connect(window.showHide)

    menu.addSeparator()

    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(QApplication.instance().quit)

    tray.setContextMenu(menu)

    # left-click on the tray icon toggles the window
    tray.activated.connect(
        lambda reason: (
            window.showHide()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
    )

    tray.show()
    return tray


def main():
    app = QApplication(sys.argv)
    # prevent the app from quitting when the window is hidden (Esc) —
    # without this, closing the last visible window exits the process.
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()

    _tray = _build_tray(window)  # keeping a reference to avoid garbage collection.

    # Adaptor parents itself to `window`; QDBusConnection finds and
    # exports it automatically (default RegisterOption is ExportAdaptors,
    # so no explicit options flag needed here).
    RephraserAdaptor(window)

    dbus = QDBusConnection.sessionBus()
    if not dbus.registerService("org.kde.rephraser"):
        print(
            "Couldn't claim org.kde.rephraser on the session bus — "
            "is another instance already running?"
        )
    dbus.registerObject("/org/kde/rephraser", window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
