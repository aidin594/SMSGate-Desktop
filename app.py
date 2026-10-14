"""SMSGate Desk Community — open-source public edition."""
from __future__ import annotations

import csv
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRect, QTimer, QThreadPool, QRunnable, QObject, Signal, Slot, QLockFile
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPalette, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QInputDialog, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QStackedWidget,
    QStyledItemDelegate, QStyle, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QVBoxLayout, QWidget, QSpinBox, QAbstractItemView, QSystemTrayIcon, QMenu,
)

from core import (
    Gateway, GatewayError, app_dir, all_messages, group_conversations, canonical_phone, canonical_display, dialing_number, iso_date,
    json_save, load_cache, load_settings, merge_items, normalize_inbox,
    normalize_sent, normalized_sim, validate_url, parse_recipients, load_templates,
    validate_template, MAX_RECIPIENTS, MAX_TEMPLATES,
)

from notification_utils import IncomingNotificationTracker, alert_content
from startup_utils import (StartupError, registered_command, registration_hint,
                           set_startup, restore_startup, startup_command, BACKGROUND_FLAG)

APP_VERSION = '1.1.0-dev'
APP_NAME = 'SMSGate Desk Community'
BASE = app_dir()
BASE.mkdir(parents=True, exist_ok=True)
LOGFILE = BASE / 'smsgate.log'
logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
    LOGFILE, maxBytes=3_000_000, backupCount=3, encoding='utf-8')],
    format='%(asctime)s %(levelname)s %(threadName)s %(message)s')
LOG = logging.getLogger('smsgatedesk')
CRASH_STREAM = open(BASE / 'fatal-python.log', 'a', encoding='utf-8')


def app_icon() -> QIcon:
    # Bundled via PyInstaller --add-data so Windows taskbar/tray icons work in onefile.
    frozen_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    for name in ('SMSGateDesk.ico', 'SMSGateDesk.png'):
        path = frozen_dir / 'assets' / name
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    LOG.warning('Bundled application icon not found; using system fallback')
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)

faulthandler.enable(file=CRASH_STREAM, all_threads=True)

from credential_store import (CredentialStoreError, read_password, save_password,
                              delete_password, credential_self_test)


class TaskBridge(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)


class Worker(QRunnable):
    def __init__(self, task_id, fn, bridge):
        super().__init__()
        self.task_id, self.fn, self.bridge = task_id, fn, bridge

    def run(self):
        try:
            result = self.fn()
            self.bridge.completed.emit(self.task_id, result)
        except Exception as exc:
            LOG.exception('Background job %s failed', self.task_id)
            self.bridge.failed.emit(self.task_id, str(exc))


class ConversationDelegate(QStyledItemDelegate):
    """Paint list rows, don't create thousands of QWidget cards on refresh."""
    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors

    def sizeHint(self, option, index):
        return QSize(315, 91)

    def paint(self, painter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole) or {}
        c = self.colors
        r = option.rect.adjusted(5, 3, -5, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c['selected'] if selected else c['panel']))
        painter.drawRoundedRect(r, 12, 12)
        avatar = QRect(r.left()+12,r.top()+14,40,40)
        painter.setBrush(QColor(c['avatar']))
        painter.drawEllipse(avatar)
        painter.setPen(QColor(c['accent']))
        font = QFont('Segoe UI',10,QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(avatar,Qt.AlignmentFlag.AlignCenter,str(data.get('initial','•'))[:2])
        tx = avatar.right()+12
        right = r.right()-12
        time = str(data.get('time',''))
        font = QFont('Segoe UI',9)
        painter.setFont(font)
        painter.setPen(QColor(c['muted']))
        tw = painter.fontMetrics().horizontalAdvance(time)
        painter.drawText(QRect(right-tw-2,r.top()+11,tw+2,22),Qt.AlignmentFlag.AlignVCenter,time)
        font = QFont('Segoe UI',11,QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(c['text']))
        title_width = max(10,right-tw-tx-9)
        title = painter.fontMetrics().elidedText(str(data.get('phone','')),Qt.TextElideMode.ElideRight,title_width)
        painter.drawText(QRect(tx,r.top()+10,title_width,24),Qt.AlignmentFlag.AlignVCenter,title)
        painter.setFont(QFont('Segoe UI',9))
        painter.setPen(QColor(c['muted']))
        snippet = painter.fontMetrics().elidedText(' '.join(str(data.get('preview','')).split()),
                                                   Qt.TextElideMode.ElideRight, max(10,right-tx))
        painter.drawText(QRect(tx,r.top()+35,right-tx,21),Qt.AlignmentFlag.AlignVCenter,snippet)
        painter.setPen(QColor(c['accent']))
        painter.drawText(QRect(tx,r.top()+60,right-tx,15),Qt.AlignmentFlag.AlignVCenter,
                         f"{data.get('sim','')}   ·   {data.get('count',0)} messages")
        painter.restore()


PALETTES = {
    'dark': dict(bg='#0A1020',sidebar='#10192C',panel='#151F32',surface='#0E1729',
      selected='#26334D',input='#0D182A',border='#293A53',text='#F0F4FA',muted='#A0AEC5',
      accent='#A697FF',accent_btn='#6657E8',avatar='#32305A',outgoing='#37316D',incoming='#1E2B3F',
      positive='#65D6AC',warn='#FFC27A'),
    'light': dict(bg='#F5F7FB',sidebar='#FFFFFF',panel='#FFFFFF',surface='#F0F3F9',
      selected='#EAE8FF',input='#FFFFFF',border='#DDE3EE',text='#17223A',muted='#66758A',
      accent='#4D45BC',accent_btn='#5649C7',avatar='#E7E5FC',outgoing='#DFDCFA',incoming='#F1F4F9',
      positive='#137C5A',warn='#96600E'),
}


def stylesheet(c):
    return f'''
QWidget {{ background:{c['bg']}; color:{c['text']};font-family:"Segoe UI"; font-size:13px; }}
QLabel {{background:transparent;}}
QFrame#sidebar {{background:{c['sidebar']};border-right:1px solid {c['border']};}}
QFrame#pane,QFrame#card {{background:{c['panel']};border:1px solid {c['border']};border-radius:14px;}}
QFrame#chatArea {{background:{c['surface']};border:1px solid {c['border']};border-radius:14px;}}
QFrame#header,QFrame#composer {{background:{c['panel']};border:0;}}
QFrame#bubbleIn {{background:{c['incoming']};border:1px solid {c['border']};border-radius:15px;}}
QFrame#bubbleOut {{background:{c['outgoing']};border:1px solid {c['border']};border-radius:15px;}}
QLabel#title {{font-size:25px;font-weight:700;}}
QLabel#subtitle,QLabel#secondary {{color:{c['muted']};}}
QLabel#chatTitle {{font-size:18px;font-weight:650;}}
QPushButton {{background:{c['surface']};border:1px solid {c['border']};border-radius:9px;padding:9px 13px;}}
QPushButton:hover {{background:{c['selected']};}}
QPushButton:disabled {{color:{c['muted']};}}
QPushButton#primary {{background:{c['accent_btn']};color:white;border:0;font-weight:650;}}
QPushButton#nav {{background:transparent;border:0;text-align:left;padding:13px 13px;font-size:14px;}}
QPushButton#nav:checked {{background:{c['selected']};color:{c['accent']};border-left:3px solid {c['accent']};}}
QLineEdit,QPlainTextEdit,QComboBox,QSpinBox {{background:{c['input']};color:{c['text']};border:1px solid {c['border']};border-radius:9px;padding:9px;selection-background-color:{c['accent_btn']};}}
QLineEdit:focus,QPlainTextEdit:focus {{border:1px solid {c['accent']};}}
QComboBox QAbstractItemView {{background:{c['panel']};color:{c['text']};selection-background-color:{c['selected']};}}
QListWidget {{background:{c['panel']};border:0;outline:0;}}
QListWidget::item:selected {{background:transparent;}}
QScrollArea {{background:{c['surface']};border:0;}}
QScrollArea#settingsScroll {{background:transparent;border:0;}}
QWidget#settingsContent {{background:{c['bg']};}}
QFrame#settingsFooter {{background:{c['bg']};border-top:1px solid {c['border']};}}
QLabel#settingsSectionTitle {{font-size:16px;font-weight:650;}}
QScrollArea>QWidget>QWidget {{background:{c['surface']};}}
QTableWidget {{background:{c['panel']};alternate-background-color:{c['surface']};gridline-color:{c['border']};border:1px solid {c['border']};}}
QHeaderView::section {{background:{c['selected']};color:{c['text']};padding:9px;border:0;}}
QTableWidget::item:selected {{background:{c['selected']};color:{c['text']};}}
QScrollBar:vertical {{width:9px;background:transparent;}}
QScrollBar::handle:vertical {{background:{c['border']};border-radius:4px;min-height:35px;}}
'''


class Bubble(QFrame):
    def __init__(self, item, color):
        super().__init__()
        outgoing = item.get('direction') == 'outgoing'
        self.setObjectName('bubbleOut' if outgoing else 'bubbleIn')
        self.setMaximumWidth(570)
        v = QVBoxLayout(self)
        v.setContentsMargins(15,11,15,9)
        v.setSpacing(7)
        txt = QLabel(str(item.get('text') or '[Message text not available from gateway]'))
        txt.setTextFormat(Qt.TextFormat.PlainText)
        txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        txt.setWordWrap(True)
        txt.setStyleSheet('background:transparent;border:0;font-size:13px;')
        if re.search('[\u0590-\u08ff]',txt.text()):
            txt.setAlignment(Qt.AlignmentFlag.AlignRight)
        v.addWidget(txt)
        status = (str(item.get('state') or '') if outgoing else '')
        sim = 'SIM '+str(item['sim']) if normalized_sim(item.get('sim')) else 'SIM unknown'
        stamp = iso_date(item.get('date')) or 'Date unknown'
        meta = QLabel('  ·  '.join(x for x in (stamp,sim,status) if x))
        meta.setObjectName('secondary')
        meta.setStyleSheet(f"background:transparent;color:{color['muted']};font-size:10px;")
        meta.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(meta)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_path = BASE/'settings.json'
        self.cache_path = BASE/'messages.json'
        self.templates_path = BASE/'templates.json'
        self.templates = load_templates(self.templates_path)
        self.settings = load_settings(self.settings_path)
        self.cache = load_cache(self.cache_path)
        self.password = ''
        self._init_password()
        self.sim = self.settings['sim']
        self.active_key = None
        self.conversation_data = {}
        self._current_signature = None
        self._limit = 100
        self._syncing = False
        self._sending = False
        self._jobs = {}
        self._callbacks = {}
        self._sequence = 0
        self._closing = False
        self._close_requested = False
        self._is_online = False
        self._last_checked = None
        self._notification_tracker = IncomingNotificationTracker()
        self._tray = None
        self._quit_requested = False
        self._tray_hint_shown = False
        self._new_message_count = 0
        self.bridge = TaskBridge(self)
        self.bridge.completed.connect(self._worker_completed,Qt.ConnectionType.QueuedConnection)
        self.bridge.failed.connect(self._worker_failed,Qt.ConnectionType.QueuedConnection)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.setWindowTitle(f'{APP_NAME}  ·  v{APP_VERSION}')
        self.setWindowIcon(app_icon())
        self.resize(1280,810)
        self.setMinimumSize(900,630)
        self.colors = PALETTES['dark']
        self._build()
        self._apply_theme()
        self._refresh_view()
        self._show_page(0)
        self._setup_tray()
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self.sync)
        self.sync_timer.start(self.settings['interval']*1000)
        QTimer.singleShot(450,self.sync)

    def _init_password(self):
        self._password_load_error = ''
        if not self.settings.get('remember_password'):
            return
        try:
            self.password = read_password(self.settings.get('url','')) or ''
        except CredentialStoreError as exc:
            self._password_load_error = str(exc)
            LOG.warning('Unable to load saved gateway credential: %s', exc)

    def _build(self):
        base = QWidget();self.setCentralWidget(base)
        row=QHBoxLayout(base);row.setContentsMargins(0,0,0,0);row.setSpacing(0)
        sidebar=QFrame(objectName='sidebar');sidebar.setFixedWidth(220)
        sv=QVBoxLayout(sidebar);sv.setContentsMargins(13,21,13,16);sv.setSpacing(7)
        self.brand=QLabel('✦   SMSGate Desk');self.brand.setStyleSheet('font-size:18px;font-weight:750;padding:12px 5px 24px;')
        sv.addWidget(self.brand)
        self.stack=QStackedWidget();self.nav=[]
        for label in ('Conversations','Sent archive','New message','Overview','Diagnostics','Settings'):
            b=QPushButton('   '+label,objectName='nav');b.setCheckable(True)
            i=len(self.nav);b.clicked.connect(lambda _=False,i=i:self._show_page(i))
            self.nav.append(b);sv.addWidget(b)
        sv.addStretch()
        self.sidebar_sim=QLabel('');self.sidebar_sim.setObjectName('secondary');sv.addWidget(self.sidebar_sim)
        self.status=QLabel('●  Not checked');self.status.setWordWrap(True);sv.addWidget(self.status)
        row.addWidget(sidebar);row.addWidget(self.stack,1)
        self._build_chats();self._build_sent();self._build_compose();self._build_overview();self._build_diag();self._build_settings()

    def page(self, title, subtitle):
        widget=QWidget();v=QVBoxLayout(widget);v.setContentsMargins(25,22,25,23);v.setSpacing(13)
        heading=QLabel(title,objectName='title');v.addWidget(heading)
        expl=QLabel(subtitle,objectName='subtitle');expl.setWordWrap(True);v.addWidget(expl)
        self.stack.addWidget(widget)
        return v

    def _show_page(self, page):
        if page == 0:
            self._new_message_count = 0
            self._update_unread_marker()
        self.stack.setCurrentIndex(page)
        for i,b in enumerate(self.nav):b.setChecked(i==page)

    def _build_chats(self):
        v=self.page('Conversations','Messages from your selected SIM, plus outgoing messages whose SIM is unknown.')
        top=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search conversations or message text…')
        top.addWidget(self.search,1)
        self.main_sim_label=QLabel('');self.main_sim_label.setObjectName('secondary');top.addWidget(self.main_sim_label)
        self.sync_button=QPushButton('↻  Sync');self.sync_button.setObjectName('primary');self.sync_button.clicked.connect(self.sync);top.addWidget(self.sync_button)
        v.addLayout(top)
        split=QSplitter(Qt.Orientation.Horizontal);split.setChildrenCollapsible(False);split.setHandleWidth(7)
        left=QFrame(objectName='pane');lv=QVBoxLayout(left);lv.setContentsMargins(7,11,7,8);lv.setSpacing(6)
        self.conversations_info=QLabel('0 conversations');self.conversations_info.setObjectName('secondary');lv.addWidget(self.conversations_info)
        self.list=QListWidget();self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setSpacing(2);self.list.currentItemChanged.connect(self._select_chat)
        lv.addWidget(self.list,1);split.addWidget(left)
        right=QFrame(objectName='chatArea');rv=QVBoxLayout(right);rv.setContentsMargins(0,0,0,0);rv.setSpacing(0)
        head=QFrame(objectName='header');hv=QVBoxLayout(head);hv.setContentsMargins(19,16,19,13)
        self.chat_name=QLabel('Choose a conversation',objectName='chatTitle');hv.addWidget(self.chat_name)
        self.chat_details=QLabel('Sync or select a contact');self.chat_details.setObjectName('secondary');hv.addWidget(self.chat_details)
        rv.addWidget(head)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.host=QWidget();self.chat_layout=QVBoxLayout(self.host)
        self.chat_layout.setContentsMargins(16,16,16,18);self.chat_layout.setSpacing(10)
        self.scroll.setWidget(self.host);rv.addWidget(self.scroll,1)
        foot=QFrame(objectName='composer');cr=QHBoxLayout(foot);cr.setContentsMargins(13,12,13,12);cr.setSpacing(9)
        self.reply_sim_label=QLabel('');self.reply_sim_label.setObjectName('secondary');cr.addWidget(self.reply_sim_label)
        self.reply=QPlainTextEdit();self.reply.setPlaceholderText('Write a reply…');self.reply.setFixedHeight(68);cr.addWidget(self.reply,1)
        self.reply_send=QPushButton('Send ↗',objectName='primary');self.reply_send.clicked.connect(self.send_reply);cr.addWidget(self.reply_send)
        rv.addWidget(foot);split.addWidget(right)
        split.setSizes([355,845]);split.setStretchFactor(0,1);split.setStretchFactor(1,3)
        v.addWidget(split,1)
        self.search_delay=QTimer(self);self.search_delay.setSingleShot(True);self.search_delay.setInterval(180)
        self.search_delay.timeout.connect(self._refresh_view)
        self.search.textChanged.connect(lambda *_:self.search_delay.start())

    def _build_sent(self):
        v=self.page('Sent archive','SMSGate outgoing messages; SIM unknown means the gateway did not report the sending SIM. Other Android SMS apps are not included.')
        h=QHBoxLayout();self.sent_search=QLineEdit();self.sent_search.setPlaceholderText('Search sent messages…');h.addWidget(self.sent_search,1)
        exp=QPushButton('Export CSV');exp.clicked.connect(self.export_sent);h.addWidget(exp);v.addLayout(h)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Time','Recipient','Message','Status','SIM'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._show_sent_detail)
        v.addWidget(self.table,1)
        self.sent_filter_timer=QTimer(self);self.sent_filter_timer.setSingleShot(True)
        self.sent_filter_timer.setInterval(180);self.sent_filter_timer.timeout.connect(self._draw_sent)
        self.sent_search.textChanged.connect(lambda *_:self.sent_filter_timer.start())
        self._table_rows=[]

    def _build_compose(self):
        v=self.page('New message','Send using the single SIM selected in Settings. No automatic sending.')
        card=QFrame(objectName='card');cv=QVBoxLayout(card);cv.setContentsMargins(22,22,22,22);cv.setSpacing(12)
        self.compose_sim_info=QLabel('');cv.addWidget(self.compose_sim_info)
        cv.addWidget(QLabel('Recipient'))
        self.recipient=QLineEdit();self.recipient.setPlaceholderText('+46701234567');cv.addWidget(self.recipient)
        cv.addWidget(QLabel('Message'))
        self.compose=QPlainTextEdit();self.compose.setPlaceholderText('Your message…');self.compose.setMinimumHeight(180);cv.addWidget(self.compose)
        self.char_count=QLabel('0 characters');self.char_count.setObjectName('secondary');cv.addWidget(self.char_count)
        self.compose.textChanged.connect(lambda:self.char_count.setText(f'{len(self.compose.toPlainText())} characters'))
        self.compose_button=QPushButton('Send message  ↗',objectName='primary');self.compose_button.clicked.connect(self.send_compose)
        cv.addWidget(self.compose_button)
        v.addWidget(card);v.addStretch()

    def _build_overview(self):
        v=self.page('Overview','Local gateway health and saved-message summary.')
        card=QFrame(objectName='card');c=QVBoxLayout(card);c.setContentsMargins(24,24,24,24)
        self.ov_status=QLabel('Not connected yet');self.ov_status.setStyleSheet('font-size:19px;font-weight:650;');c.addWidget(self.ov_status)
        self.ov_details=QLabel('');self.ov_details.setWordWrap(True);self.ov_details.setObjectName('secondary');c.addWidget(self.ov_details)
        test=QPushButton('Check & sync now',objectName='primary');test.clicked.connect(self.sync);c.addWidget(test)
        v.addWidget(card)
        self.ov_counts=QLabel('');v.addWidget(self.ov_counts)
        warning=QLabel('Incoming messages use the selected SIM. Previously sent SMS without SIM metadata are shown as SIM unknown when enabled. They may belong to either SIM.')
        warning.setWordWrap(True);warning.setObjectName('secondary');v.addWidget(warning);v.addStretch()

    def _build_diag(self):
        v=self.page('Diagnostics','Non-sensitive connectivity and error information. No SMS is sent by this page.')
        buttons=QHBoxLayout();test=QPushButton('Check gateway',objectName='primary');test.clicked.connect(self.sync);buttons.addWidget(test)
        log=QPushButton('Open log folder');log.clicked.connect(self.open_logs);buttons.addWidget(log);buttons.addStretch();v.addLayout(buttons)
        self.diagnostics=QPlainTextEdit();self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlainText('App log: '+str(LOGFILE)+'\n\nWaiting for first connection check…')
        v.addWidget(self.diagnostics,1)

    def _build_settings(self):
        """Responsive, scrollable settings; save action stays visible at any height.

        The old QFormLayout put full-length checkbox text in an unbreakable
        field column. At 900px window width the form's minimum-size hint
        exceeded the usable viewport, clipping inputs and both action buttons.
        """
        v = self.page('Settings', 'Choose the SIM once. All conversations, archives and outgoing SMS follow that choice.')

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName('settingsScroll')
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_content = QWidget(objectName='settingsContent')
        content = QVBoxLayout(self.settings_content)
        content.setContentsMargins(0, 0, 10, 12)
        content.setSpacing(13)

        def section(title, description):
            card = QFrame(objectName='card')
            body = QVBoxLayout(card)
            body.setContentsMargins(19, 17, 19, 19)
            body.setSpacing(11)
            header = QLabel(title, objectName='settingsSectionTitle')
            body.addWidget(header)
            info = QLabel(description, objectName='secondary')
            info.setWordWrap(True)
            body.addWidget(info)
            content.addWidget(card)
            return body

        def field(body, label, control, detail=''):
            line = QHBoxLayout()
            line.setSpacing(12)
            caption = QLabel(label)
            caption.setFixedWidth(120)
            line.addWidget(caption, 0, Qt.AlignmentFlag.AlignTop)
            right = QVBoxLayout()
            right.setSpacing(5)
            control.setMinimumWidth(0)
            right.addWidget(control)
            if detail:
                hint = QLabel(detail, objectName='secondary')
                hint.setWordWrap(True)
                right.addWidget(hint)
            line.addLayout(right, 1)
            body.addLayout(line)

        def option(body, title, checked, description):
            control = QCheckBox(title)
            control.setChecked(bool(checked))
            body.addWidget(control)
            hint = QLabel(description, objectName='secondary')
            hint.setWordWrap(True)
            hint.setContentsMargins(22, 0, 0, 2)
            body.addWidget(hint)
            return control

        gateway = section('Connection', 'The local address of the Android SMSGate server. The password stays in Windows Credential Manager.')
        self.url = QLineEdit(str(self.settings['url']))
        field(gateway, 'Gateway address', self.url)
        warning = QLabel('Security: HTTP sends login details and SMS over your local network without encryption. Use a trusted LAN, or HTTPS with a valid certificate. Message history is stored unencrypted on this PC.')
        warning.setWordWrap(True)
        warning.setObjectName('secondary')
        gateway.addWidget(warning)
        self.username = QLineEdit(str(self.settings['user']))
        field(gateway, 'Username', self.username)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText('Leave blank to keep stored password' if self.password else 'Enter gateway password')
        field(gateway, 'Password', self.secret)
        self.remember = option(gateway, 'Remember password', self.settings['remember_password'],
                               'Store securely using Windows Credential Manager; the password is not written to settings.json.')
        self.password_status = QLabel(objectName='secondary')
        self.password_status.setWordWrap(True)
        field(gateway, 'Password storage', self.password_status)
        self._refresh_password_status()

        sim = section('SIM card & conversations', 'All sending uses the selected SIM. Messages from the other SIM stay separate.')
        self.selected_sim = QComboBox()
        self.selected_sim.addItems(['SIM 1', 'SIM 2'])
        self.selected_sim.setCurrentIndex(self.sim - 1)
        field(sim, 'Active SIM', self.selected_sim)
        self.country_code = QLineEdit(str(self.settings.get('country_code', '')))
        self.country_code.setPlaceholderText('e.g. 46 (Sweden), 1 (US), 98 (Iran)')
        self.country_code.setMaxLength(3)
        field(sim, 'Dialing country code', self.country_code)
        country_hint = QLabel('Optional. Enter 1–3 digits without + to match local 0-prefixed numbers with international numbers. Leave blank to use explicit +country numbers only.')
        country_hint.setWordWrap(True)
        country_hint.setObjectName('secondary')
        sim.addWidget(country_hint)
        self.unknown = option(sim, 'Include incoming SMS with unknown SIM', self.settings['include_unknown_sim'],
                              'These messages might belong to either SIM. Leave off for strict SIM filtering.')
        self.unassigned_sent = option(sim, 'Show outgoing SMS with unknown SIM', self.settings['show_unassigned_sent'],
                                      'Some gateway send records have no SIM number. Display them without assigning a SIM.')

        appearance = section('Appearance & sync', 'Choose the look and how often the desktop checks your phone.')
        self.theme_select = QComboBox()
        self.theme_select.addItems(['Dark', 'Light', 'System'])
        self.theme_select.setCurrentText(self.settings['theme'].title())
        field(appearance, 'Theme', self.theme_select)
        self.interval = QSpinBox()
        self.interval.setRange(20, 3600)
        self.interval.setSuffix(' seconds')
        self.interval.setValue(self.settings['interval'])
        field(appearance, 'Sync interval', self.interval)

        notifications = section('Notifications & background', 'Alerts are shown only while this application is running.')
        self.notify_toggle = option(notifications, 'Notify about new SMS', self.settings['desktop_notifications'],
                                    'Only messages from the selected SIM produce desktop notifications.')
        self.notify_preview = option(notifications, 'Include SMS text in notifications', self.settings['notification_preview'],
                                     'Message previews can be read by anyone who can see the Windows screen.')
        self.close_to_tray = option(notifications, 'Continue running in system tray', self.settings['close_to_tray'],
                                    'Closing the main window keeps syncing and receiving alerts; exit from the tray menu.')

        # The Windows registry is authoritative. Detect and explain paths from old EXE copies.
        try:
            self._startup_command_at_load = registered_command()
            startup_checked = self._startup_command_at_load is not None
            startup_message = registration_hint(self._startup_command_at_load)
        except StartupError as exc:
            self._startup_command_at_load = None
            startup_checked = self.settings['start_with_windows']
            startup_message = f'Could not read Windows startup settings: {exc}'
        self.start_with_windows = option(notifications, 'Start automatically with Windows', startup_checked,
                                         'Launch in the system tray when you sign in. No admin rights required. Disable here to undo.')
        self.startup_status = QLabel(startup_message, objectName='secondary')
        self.startup_status.setWordWrap(True)
        notifications.addWidget(self.startup_status)
        test_alert = QPushButton('Send test notification (no SMS)')
        test_alert.clicked.connect(self._test_notification)
        notifications.addWidget(test_alert, 0, Qt.AlignmentFlag.AlignLeft)

        content.addStretch(1)
        self.settings_scroll.setWidget(self.settings_content)
        v.addWidget(self.settings_scroll, 1)

        # Sticky action area: remains visible even when the options scroll.
        footer = QFrame(objectName='settingsFooter')
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(0, 12, 0, 0)
        footer_row.setSpacing(10)
        note = QLabel('Changes take effect after saving.', objectName='secondary')
        note.setWordWrap(True)
        footer_row.addWidget(note, 1)
        self.settings_save_button = QPushButton('Save settings', objectName='primary')
        self.settings_save_button.setMinimumWidth(152)
        self.settings_save_button.clicked.connect(self.save_settings)
        footer_row.addWidget(self.settings_save_button)
        v.addWidget(footer, 0)

    def _setup_tray(self):
        """A system tray keeps polling active when the window is hidden."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            LOG.warning('Windows system tray unavailable; close-to-tray and toast disabled')
            return
        try:
            tray=QSystemTrayIcon(self.windowIcon(), self)
            tray.setToolTip(f'{APP_NAME} — SIM {self.sim}')
            menu=QMenu(self)
            a_open=menu.addAction('Open SMSGate Desk')
            a_open.triggered.connect(self._show_from_tray)
            a_sync=menu.addAction('Sync now')
            a_sync.triggered.connect(self.sync)
            menu.addSeparator()
            a_exit=menu.addAction('Exit SMSGate Desk')
            a_exit.triggered.connect(self._quit_from_tray)
            tray.setContextMenu(menu)
            tray.activated.connect(self._tray_activated)
            tray.messageClicked.connect(self._open_notification)
            tray.show()
            self._tray=tray
        except Exception:
            LOG.exception('Could not start system tray icon')
            self._tray=None

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self._show_from_tray()

    def _show_from_tray(self, *unused):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _open_notification(self, *unused):
        self._show_from_tray()
        self._show_page(0)

    def _quit_from_tray(self, *unused):
        self._quit_requested = True
        self.close()

    def _update_unread_marker(self):
        if not hasattr(self,'nav'):
            return
        n=self._new_message_count
        self.nav[0].setText('   Conversations' + (f'  ({n})' if n else ''))
        if self._tray is not None:
            self._tray.setToolTip(f'{APP_NAME} — SIM {self.sim}' + (f' — {n} new SMS' if n else ''))

    def _show_notification(self, title, message):
        if self._tray is None or not self._tray.isVisible():
            LOG.warning('Notification unavailable: tray icon is not active')
            return False
        try:
            self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 10000)
            return True
        except Exception:
            LOG.exception('Could not request a Windows notification')
            return False

    def _notify_incoming(self, incoming):
        title,message=alert_content(incoming, self.settings['notification_preview'])
        self._show_notification(title, message)

    def _test_notification(self):
        success=self._show_notification('SMSGate Desk — Test',
               f'Notifications are set up for SIM {self.selected_sim.currentIndex()+1}. No SMS was sent.')
        if success:
            self._record_diag('Test notification requested. Windows notification settings control visibility.')
        else:
            QMessageBox.warning(self, APP_NAME, 'Windows tray notifications are unavailable. Check Windows taskbar and notification settings.')

    def _refresh_password_status(self):
        if self._password_load_error:
            status = 'Could not retrieve saved password: ' + self._password_load_error
        elif self.settings.get('remember_password') and self.password:
            status = 'Saved in Windows Credential Manager (verified when last saved).'
        elif self.settings.get('remember_password'):
            status = 'Remember is enabled but no stored password was found. Enter it and Save settings.'
        else:
            status = 'Not saved. Enable Keep password and click Save settings to persist after restart.'
        self.password_status.setText(status)

    def _theme_key(self):
        mode=self.settings['theme']
        if mode=='system':
            # User can also explicitly choose Light or Dark, independent of Windows.
            pal=QApplication.styleHints().colorScheme()
            return 'dark' if pal == Qt.ColorScheme.Dark else 'light'
        return mode

    def _apply_theme(self):
        self.colors=PALETTES[self._theme_key()]
        QApplication.instance().setStyleSheet(stylesheet(self.colors))
        self.list.setItemDelegate(ConversationDelegate(self.colors,self.list))
        self.brand.setStyleSheet(f"font-size:18px;font-weight:750;color:{self.colors['accent']};padding:12px 5px 24px;")
        self._paint_status()

    def _paint_status(self):
        online=self._is_online
        self.status.setStyleSheet(f"color:{self.colors['positive'] if online else self.colors['muted']};font-size:12px;")
        self.status.setText(('●  Connected' if online else '●  Offline / cached') + f'\nSIM {self.sim}' + (f' · Checked {self._last_checked}' if self._last_checked else ''))

    def _record_diag(self,text):
        self.diagnostics.appendPlainText(datetime.now().strftime('%H:%M:%S')+'  '+str(text))

    def _show_error(self, text):
        LOG.warning('User-visible operation failed: %s',text)
        QMessageBox.warning(self,'SMSGate Desk',str(text))

    def save_settings(self):
        try:
            url=validate_url(self.url.text())
            user=self.username.text().strip()
            if not user:raise ValueError('Username cannot be empty.')
            manually_entered=self.secret.text()
            password=manually_entered or self.password
            if (url != self.settings['url'] or user != self.settings['user']) and not manually_entered:
                raise ValueError('Gateway address or username changed. Enter the password again to avoid using credentials for the previous account.')
            country_code = self.country_code.text().strip().lstrip('+')
            if country_code and not re.fullmatch(r'[1-9][0-9]{0,2}', country_code):
                raise ValueError('Dialing country code must be 1–3 digits (without +).')
            desired_startup = self.start_with_windows.isChecked()
            # Do not accept a registry entry pointing at an arbitrary copy.
            # If the checkbox is on, resolve the command from the actual packaged EXE.
            requested_command = startup_command() if desired_startup else None
            previous_command = registered_command()
            new_settings={
                'url':url,'user':user,'interval':self.interval.value(),'country_code':country_code,
                'sim':self.selected_sim.currentIndex()+1,
                'theme':self.theme_select.currentText().lower(),
                'remember_password':self.remember.isChecked(),
                'include_unknown_sim':self.unknown.isChecked(),
                'show_unassigned_sent':self.unassigned_sent.isChecked(),
                'desktop_notifications':self.notify_toggle.isChecked(),
                'notification_preview':self.notify_preview.isChecked(),
                'close_to_tray':self.close_to_tray.isChecked(),
                'start_with_windows':desired_startup,
            }
            if self.remember.isChecked():
                if not password:
                    raise ValueError('Enter a password before enabling Remember password.')
                save_password(url,password)  # Native WinCred: verifies read-after-write.
            # Atomic preference change w.r.t. the Windows startup entry: roll back
            # registry state if persisting settings fails (e.g. disk full).
            startup_changed = (requested_command != previous_command)
            if startup_changed:
                set_startup(desired_startup, requested_command)
            try:
                json_save(self.settings_path,new_settings)
            except Exception:
                if startup_changed:
                    try:
                        restore_startup(previous_command)
                    except StartupError:
                        LOG.exception('Failed to restore previous Windows startup setting')
                raise
            urls_to_delete = []
            if not self.remember.isChecked():
                urls_to_delete.append(url)
            if url != self.settings['url']:
                urls_to_delete.append(self.settings['url'])
            for obsolete_url in set(urls_to_delete):
                try:
                    delete_password(obsolete_url)
                except CredentialStoreError as exc:
                    LOG.warning('Could not delete stored credential: %s', exc)
                    self._record_diag('Warning: old Windows credential could not be deleted. Check log.')
            old_sim=self.sim
            self.settings=new_settings;self.password=password;self.sim=new_settings['sim']
            self._password_load_error=''
            self.secret.clear()
            self.secret.setPlaceholderText('Leave blank to keep stored password' if new_settings['remember_password'] else 'Enter gateway password')
            self._refresh_password_status()
            self.startup_status.setText(registration_hint(registered_command()))
            self.sync_timer.setInterval(self.settings['interval']*1000)
            self._apply_theme()
            self._update_unread_marker()
            if old_sim!=self.sim:
                self.active_key=None;self.reply.clear();self._limit=100
            self._current_signature=None
            self._refresh_view()
            self._record_diag(f'Settings saved · SIM {self.sim} · {self.settings["theme"]} appearance')
            self.sync()
        except (ValueError,OSError,CredentialStoreError,StartupError) as exc:
            self._show_error(str(exc))

    def _gateway(self):
        if not self.password:
            raise GatewayError('Enter and save the gateway password in Settings.')
        return Gateway(self.settings['url'],self.settings['user'],self.password)

    def _run(self,fn,ok,fail):
        self._sequence+=1
        task_id=self._sequence
        worker=Worker(task_id,fn,self.bridge)
        self._jobs[task_id]=worker
        self._callbacks[task_id]=(ok,fail)
        self.pool.start(worker)

    @Slot(int,object)
    def _worker_completed(self,task_id,result):
        self._jobs.pop(task_id,None)
        callbacks=self._callbacks.pop(task_id,None)
        if callbacks and not self._closing:
            try:callbacks[0](result)
            except Exception:
                LOG.exception('Error while applying background result')
                self._record_diag('UI update error; check log')
        self._maybe_close()

    @Slot(int,str)
    def _worker_failed(self,task_id,err):
        self._jobs.pop(task_id,None)
        callbacks=self._callbacks.pop(task_id,None)
        if callbacks and not self._closing:
            try:callbacks[1](err)
            except Exception:LOG.exception('Error while reporting background failure')
        self._maybe_close()

    def _maybe_close(self):
        if self._close_requested and not self._jobs:
            self._closing=True
            QTimer.singleShot(0,self.close)

    def sync(self):
        if self._syncing or self._closing or self._close_requested:
            return
        try:gateway=self._gateway()
        except (GatewayError,ValueError) as exc:
            self._is_online=False;self._paint_status()
            self.ov_status.setText('Password required')
            self.ov_details.setText(str(exc))
            return
        self._syncing=True;self.sync_button.setEnabled(False);self.sync_button.setText('Syncing…')
        self._record_diag('Sync started')
        self._run(gateway.sync,self._sync_complete,self._sync_failed)

    def _sync_complete(self,result):
        self._syncing=False;self.sync_button.setEnabled(True);self.sync_button.setText('↻  Sync')
        errors=result.get('errors') or {}
        health=result.get('health')
        self._last_checked=datetime.now().strftime('%H:%M')
        self._is_online = isinstance(health,dict) and str(health.get('status','')).lower() in ('pass','ok')
        if not self._is_online and (result.get('inbox') is not None or result.get('sent') is not None):
            self._is_online = True
        self._paint_status()
        changed=[]
        try:
            just_arrived=[]
            if isinstance(result.get('inbox'),list):
                rows=[normalize_inbox(x) for x in result['inbox'] if isinstance(x,dict)]
                # Only successful inbox fetches advance the baseline. First successful
                # fetch after startup is quiet; thereafter, only new IDs notify.
                just_arrived=self._notification_tracker.ingest(
                    rows, self.sim, self.settings['include_unknown_sim'])
                self.cache['inbox']=merge_items(self.cache['inbox'],rows,country_code=self.settings['country_code'])
                changed.append('Inbox '+str(len(rows)))
            if isinstance(result.get('sent'),list):
                msgs=[]
                for item in result['sent']:
                    if isinstance(item,dict):msgs.extend(normalize_sent(item))
                # Preserve SIM of locally queued sends if the server omits it.
                by_id={str(x.get('id')):x for x in self.cache['local_sent'] if x.get('id')}
                for x in msgs:
                    previous=by_id.get(x.get('id'))
                    if previous and x.get('sim') is None:x['sim']=previous.get('sim')
                    if previous and not x.get('text'):x['text']=previous.get('text','')
                self.cache['sent']=merge_items(self.cache['sent'],msgs,country_code=self.settings['country_code'])
                changed.append('Sent '+str(len(msgs)))
            if changed:
                json_save(self.cache_path,self.cache)
            self._refresh_view()
            self._record_diag(' · '.join(changed) if changed else 'No collections updated')
            if just_arrived:
                self._new_message_count += len(just_arrived)
                self._update_unread_marker()
                if self.settings['desktop_notifications']:
                    self._notify_incoming(just_arrived)
        except (OSError,ValueError,TypeError) as exc:
            LOG.exception('Cache merge failed')
            self._record_diag('Local cache problem: '+str(exc))
        self.ov_status.setText('Gateway online' if self._is_online else 'Gateway offline')
        version=health.get('version','unknown') if isinstance(health,dict) else 'unknown'
        self.ov_details.setText(f'Local device: {self.settings["url"]}  ·  Gateway version: {version}')
        for name,err in errors.items():self._record_diag(f'{name}: {err}')

    def _sync_failed(self,err):
        self._syncing=False;self.sync_button.setEnabled(True);self.sync_button.setText('↻  Sync')
        self._is_online=False;self._last_checked=datetime.now().strftime('%H:%M');self._paint_status();self._record_diag('Sync failed: '+err)

    def _visible_messages(self):
        return all_messages(self.cache, self.sim, self.settings['include_unknown_sim'],
                            self.settings['show_unassigned_sent'], self.settings['country_code'])

    def _refresh_view(self):
        term=self.search.text().strip().casefold()
        rows=self._visible_messages()
        grouped=group_conversations(rows, country_code=self.settings['country_code'])
        # Search filters conversations, not individual messages: opening a result
        # must keep the full conversational context visible.
        if term:
            grouped={key:items for key,items in grouped.items()
                     if (canonical_phone(term, self.settings['country_code']) == key and len(term) >= 6) or any(term in (str(m.get('phone',''))+' '+str(m.get('text',''))+' '+str(m.get('date',''))).casefold()
                            for m in items)}
        ordered=sorted(grouped.items(),key=lambda x:str(x[1][-1].get('date','')),reverse=True)
        self.conversation_data=dict(ordered)
        self.list.blockSignals(True)
        self.list.clear()
        current_row=-1
        for i,(key,msgs) in enumerate(ordered):
            last=msgs[-1]
            time=iso_date(last.get('date'))
            time=time[11:16] if time.startswith(datetime.now().strftime('%Y-%m-%d')) else time[:10]
            rawphone=canonical_display(last['phone'], self.settings['country_code']);preview=str(last.get('text',''))
            slot=normalized_sim(last.get('sim'))
            metadata={'key':key,'initial':''.join(c for c in rawphone if c.isalnum())[:2],
                      'phone':rawphone,'preview':preview,'time':time,
                      'sim':f'SIM {slot}' if slot else 'SIM unknown','count':len(msgs)}
            item=QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole,metadata)
            item.setToolTip(rawphone+'\n'+preview[:250])
            self.list.addItem(item)
            if key==self.active_key:current_row=i
        if current_row<0 and ordered:current_row=0
        if current_row>=0:
            self.list.setCurrentRow(current_row)
            self.active_key=ordered[current_row][0]
        else:self.active_key=None
        self.list.blockSignals(False)
        self.conversations_info.setText(f'{len(ordered)} conversations')
        self._render_chat()
        self._draw_sent()
        self.ov_counts.setText(f'Cached: {len(self.cache["inbox"])} incoming · {len(self.cache["sent"])} gateway-sent · {len(self.cache["local_sent"])} local sends')
        self.main_sim_label.setText(f'●  SIM {self.sim}' + (' + unassigned sent' if self.settings['show_unassigned_sent'] else ' only'))
        self.reply_sim_label.setText(f'SIM {self.sim}')
        self.sidebar_sim.setText(f'ACTIVE SIM   {self.sim}')
        self.compose_sim_info.setText(f'All outgoing SMS use SIM {self.sim}  ·  Change in Settings')

    def _select_chat(self,current,previous=None):
        if current is None:return
        meta=current.data(Qt.ItemDataRole.UserRole) or {}
        if self.active_key!=meta.get('key'):
            self.active_key=meta.get('key');self._limit=100;self._current_signature=None
        self._render_chat()

    def _clear_chat(self):
        while self.chat_layout.count():
            item=self.chat_layout.takeAt(0)
            if item.widget() is not None:item.widget().deleteLater()
            elif item.layout() is not None:
                # Row layouts are owned by wrapper widgets in this implementation.
                pass

    def _render_chat(self):
        msgs=self.conversation_data.get(self.active_key,[])
        signature=(self.active_key,self._limit,tuple((x.get('id'),x.get('date'),x.get('state'),x.get('text')) for x in msgs[-self._limit:]))
        if signature==self._current_signature:return
        self._current_signature=signature
        self._clear_chat()
        if not msgs:
            self.chat_name.setText('No conversation selected')
            self.chat_details.setText('Choose a conversation or sync messages.')
            self.reply.setEnabled(False);self.reply_send.setEnabled(False)
            return
        self.chat_name.setText(canonical_display(msgs[-1].get('phone',''), self.settings['country_code']))
        unknown_sent = sum(x.get('direction') == 'outgoing' and normalized_sim(x.get('sim')) is None for x in msgs)
        self.chat_details.setText(f'{len(msgs)} messages  ·  SIM {self.sim}' +
                                  (f'  ·  {unknown_sent} outgoing with SIM unknown' if unknown_sent else ''))
        self.reply.setEnabled(True);self.reply_send.setEnabled(not self._sending)
        if len(msgs)>self._limit:
            more=QPushButton(f'Load older messages ({len(msgs)-self._limit} remaining)')
            more.clicked.connect(self._load_older)
            self.chat_layout.addWidget(more,alignment=Qt.AlignmentFlag.AlignHCenter)
        previous_day=None
        for msg in msgs[-self._limit:]:
            time=iso_date(msg.get('date'))
            day=time[:10]
            if day!=previous_day:
                label=QLabel(day)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet(f"color:{self.colors['muted']};padding:10px;background:transparent;")
                self.chat_layout.addWidget(label)
                previous_day=day
            outgoing=msg.get('direction')=='outgoing'
            wrap=QWidget();h=QHBoxLayout(wrap);h.setContentsMargins(2,1,2,1)
            if outgoing:h.addStretch()
            h.addWidget(Bubble(msg,self.colors))
            if not outgoing:h.addStretch()
            self.chat_layout.addWidget(wrap)
        self.chat_layout.addStretch()
        QTimer.singleShot(0,self._scroll_bottom)

    def _scroll_bottom(self):
        if self.isVisible() and not self._closing:
            bar=self.scroll.verticalScrollBar();bar.setValue(bar.maximum())

    def _load_older(self):
        self._limit+=100
        self._render_chat()

    def _draw_sent(self,*_):
        if not hasattr(self,'table'):return
        search=self.sent_search.text().strip().casefold()
        items=[x for x in self._visible_messages() if x.get('direction')=='outgoing']
        if search:items=[x for x in items if search in ' '.join(str(x.get(k,'')) for k in ('phone','text','state')).casefold()]
        self._table_rows=items[-1500:][::-1]
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(self._table_rows))
            for r,entry in enumerate(self._table_rows):
                for c,value in enumerate((iso_date(entry.get('date')) or 'Date unknown',entry.get('phone',''),entry.get('text',''),entry.get('state',''),
                                          ('SIM '+str(entry['sim']) if normalized_sim(entry.get('sim')) else 'SIM unknown'))):
                    cell=QTableWidgetItem(str(value))
                    cell.setToolTip(str(value)[:400])
                    self.table.setItem(r,c,cell)
        finally:self.table.setUpdatesEnabled(True)

    def _show_sent_detail(self,*_):
        index=self.table.currentRow()
        if 0<=index<len(self._table_rows):
            x=self._table_rows[index]
            QMessageBox.information(self,'Sent message',f"{x.get('phone','')}\n{iso_date(x.get('date'))}\n{x.get('state','')}\nSIM {x.get('sim') or '?'}\n\n{x.get('text','')}")

    def export_sent(self):
        file,_=QFileDialog.getSaveFileName(self,'Save sent archive','sent_messages.csv','CSV files (*.csv)')
        if not file:return
        try:
            with open(file,'w',encoding='utf-8-sig',newline='') as f:
                fields=['id','date','phone','text','state','sim','direction']
                out=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');out.writeheader()
                out.writerows(x for x in self._visible_messages() if x.get('direction')=='outgoing')
        except OSError as exc:self._show_error('Cannot export CSV: '+str(exc))

    def send_reply(self):
        msgs=self.conversation_data.get(self.active_key,[])
        if msgs:self._send(canonical_display(msgs[-1].get('phone',''), self.settings['country_code']),self.reply.toPlainText(),clear=self.reply)

    def send_compose(self):
        self._send(self.recipient.text().strip(),self.compose.toPlainText(),clear=self.compose)

    def _send(self,phone,text,clear):
        if self._sending:return
        text=text.strip()
        destination=dialing_number(phone, self.settings['country_code'])
        if not destination:
            return self._show_error('Enter a valid recipient. Contact names and alphanumeric SMS sender IDs cannot receive replies.')
        phone=destination
        if not text:return self._show_error('Write a message first.')
        try:gateway=self._gateway()
        except (GatewayError,ValueError) as exc:return self._show_error(str(exc))
        sim=self.sim  # Snapshot selected SIM: never infer or override from conversation.
        confirmation=QMessageBox.question(self,'Confirm SMS',f'Send to {phone} via SIM {sim}?\n\n{text[:550]}',
                            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if confirmation != QMessageBox.StandardButton.Yes:return
        self._sending=True;self.compose_button.setEnabled(False);self.reply_send.setEnabled(False)
        self._record_diag(f'Sending request to {phone} using SIM {sim}')

        def done(response):
            self._sending=False;self.compose_button.setEnabled(True);self.reply_send.setEnabled(True)
            rid=response.get('id') if isinstance(response,dict) else None
            new={'id':str(rid or 'local-'+datetime.now().isoformat()),
                 'date':datetime.now().astimezone().isoformat(timespec='seconds'),
                 'phone':phone,'text':text,'sim':sim,'state':'Queued (accepted by API)',
                 'direction':'outgoing'}
            self.cache['local_sent']=merge_items(self.cache['local_sent'],[new],country_code=self.settings['country_code'])
            try:json_save(self.cache_path,self.cache)
            except OSError:LOG.exception('Could not persist queued outgoing message')
            clear.clear();self._current_signature=None;self._refresh_view()
            self._record_diag(f'SMS accepted for {phone}; delivery not yet confirmed')
            QMessageBox.information(self,'Request accepted',f'SMSGate accepted the send request via SIM {sim}.\nThis is not a delivery confirmation.')
            QTimer.singleShot(1100,self.sync)

        def failed(err):
            self._sending=False;self.compose_button.setEnabled(True);self.reply_send.setEnabled(True)
            self._record_diag('Send request failed or timed out')
            self._show_error(err)

        self._run(lambda:gateway.send(phone,text,sim),done,failed)

    def open_logs(self):
        # QDesktopServices instead of shell or subprocess.
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(BASE)))

    def closeEvent(self,event):
        # Window X hides to tray by user preference, keeping notifications alive.
        # The tray Exit action always terminates the app.
        if (not self._closing and not self._quit_requested and
                self.settings['close_to_tray'] and self._tray is not None and
                self._tray.isVisible()):
            self.hide()
            event.ignore()
            if not self._tray_hint_shown:
                self._tray_hint_shown=True
                self._show_notification(APP_NAME, 'Still running near the clock. Right-click the tray icon and choose Exit to stop.')
            return
        if self._jobs and not self._closing:
            self._close_requested=True
            self.sync_timer.stop()
            self.status.setText('Finishing network request before exit…')
            self.hide()
            event.ignore()
            return
        self.sync_timer.stop()
        if self._tray is not None:
            self._tray.hide()
        event.accept()
        # A previously hidden window is not the last *visible* window. Qt may
        # otherwise stay alive after Exit in the tray menu.
        if self._quit_requested or not self.settings['close_to_tray']:
            QTimer.singleShot(0, QApplication.instance().quit)


def exception_hook(exc_type,exc_value,exc_tb):
    try:LOG.critical('Uncaught main thread error\n%s',''.join(traceback.format_exception(exc_type,exc_value,exc_tb)))
    except Exception:pass
    # Qt callbacks may not exit the process; preserve log and avoid infinite dialogs.


def main():
    sys.excepthook=exception_hook
    if hasattr(threading,'excepthook'):
        def thread_hook(args):exception_hook(args.exc_type,args.exc_value,args.exc_traceback)
        threading.excepthook=thread_hook
    if sys.platform == 'win32':
        # Stable taskbar grouping for the EXE/shortcuts.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SMSGateDesk.Community')
        except Exception:
            LOG.exception('Unable to set Windows taskbar application ID')
    background_launch = BACKGROUND_FLAG in sys.argv
    # Remove our private flag before passing arguments to Qt.
    qt_args = [arg for arg in sys.argv if arg != BACKGROUND_FLAG]
    app=QApplication(qt_args)
    app.setStyle('Fusion')
    app.setWindowIcon(app_icon())
    # Prevent simultaneous Community instances from writing the same cache.
    lock=QLockFile(str(BASE/'running-v4.lock'))
    # Qt's default stale-lock recovery lets the app reopen after an abnormal exit.
    if not lock.tryLock(100):
        # A login-time autostart must never interrupt the user's desktop.
        if not background_launch:
            QMessageBox.information(None,APP_NAME,'SMSGate Desk is already running. Close the other instance first.')
        return 0
    try:
        window=Window()
        tray_ready = window._tray is not None and window._tray.isVisible()
        if background_launch and tray_ready:
            # Windows logon launch stays silent, syncs in the background and
            # can always be opened from the system tray.
            app.setQuitOnLastWindowClosed(False)
            LOG.info('Started with Windows: hidden system tray mode')
        else:
            # If the notification area is unavailable, NEVER run invisibly.
            window.show()
            if background_launch:
                LOG.warning('Autostart tray unavailable; opening main window instead')
        result=app.exec()
        return result
    finally:
        lock.unlock()
        CRASH_STREAM.flush()


if __name__=='__main__':
    if '--credential-self-test' in sys.argv:
        try:
            credential_self_test()
            LOG.info('Native Windows credential EXE self-test passed')
            sys.exit(0)
        except Exception:
            LOG.exception('Native Windows credential EXE self-test failed')
            sys.exit(23)
    sys.exit(main())
