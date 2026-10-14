"""Run on Windows after installing PySide6: python tests/gui_smoke.py"""
import os
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'windows' if os.environ.get('SMSGATE_SCREENSHOT_DIR') else 'offscreen'
tmp=tempfile.TemporaryDirectory(prefix='smsgate-smoke-')
os.environ['LOCALAPPDATA']=tmp.name
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from PySide6.QtWidgets import QApplication
import app as app_module
from app import Window
from unittest.mock import patch

# Never read, write or delete the user's REAL Windows credentials during QA.
_fake_credentials = {}
read_patch = patch.object(app_module, 'read_password', side_effect=lambda url: _fake_credentials.get(url))
write_patch = patch.object(app_module, 'save_password', side_effect=lambda url, pwd: _fake_credentials.__setitem__(url, pwd))
delete_patch = patch.object(app_module, 'delete_password', side_effect=lambda url: _fake_credentials.pop(url, None))
sync_patch = patch.object(Window, 'sync', lambda self: None)  # No network traffic in GUI QA.
# Never touch the REAL HKCU\...\Run key during smoke tests.
_fake_startup = {'command': None}
startup_read = patch.object(app_module, 'registered_command', side_effect=lambda: _fake_startup['command'])
startup_write = patch.object(app_module, 'set_startup', side_effect=lambda enabled, command=None:
                             _fake_startup.__setitem__('command', command if enabled else None))
startup_restore = patch.object(app_module, 'restore_startup', side_effect=lambda command:
                               _fake_startup.__setitem__('command', command))
startup_cmd = patch.object(app_module, 'startup_command', return_value='"C:\\SMSGateDeskCommunity.exe" --background')
for patched in (read_patch, write_patch, delete_patch, sync_patch, startup_read, startup_write, startup_restore, startup_cmd):
    patched.start()

app=QApplication([])
app.setStyle('Fusion')
window=Window()
window.sync_timer.stop()
window.url.setText('http://192.168.1.10:8080')
window.username.setText('sms')
window.secret.setText('GUI-test-only-secret')
window.country_code.setText('46')
assert not window.windowIcon().isNull(), 'App icon should load in source build'
# No app.exec(): do not start the deferred automatic network sync.
window.cache['inbox']=[
 {'id':'a','phone':'+46701111111','date':'2026-10-08T11:00:00+02:00','sim':1,'text':'Hej SIM1','direction':'incoming','state':'SMS'},
 {'id':'b','phone':'+46702222222','date':'2026-10-08T12:00:00+02:00','sim':2,'text':'سلام SIM2','direction':'incoming','state':'SMS'},
]
window._refresh_view()
assert window.list.count()==1
assert window.active_key=='46701111111'
window.selected_sim.setCurrentIndex(1)
window.theme_select.setCurrentText('Light')
window.save_settings()
assert window.settings['country_code']=='46'
assert window.sim==2
assert window.settings['theme']=='light'
assert window.list.count()==1
assert window.active_key=='46702222222'
assert 'SIM 2' in window.compose_sim_info.text()
# Mixed-format incoming/outgoing phone variants are one conversation.
window.cache['inbox'].append({'id':'c','phone':'070 222 22 22','date':'2026-10-08T12:01:00+02:00','sim':2,'text':'Hej igen','direction':'incoming','state':'SMS'})
window._refresh_view()
assert window.list.count()==1, 'Phone variants must not create duplicate conversations'
assert len(window.conversation_data['46702222222'])==2
window.search.setText('0046702222222')
window.search_delay.stop()
window._refresh_view()
assert window.list.count()==1, 'Search must find the conversation by equivalent international format'

# Regression: SMSGate /messages usually has no SIM, so outgoing must not vanish.
from core import normalize_sent
window.cache['sent']=normalize_sent({
    'id':'historical-sent','state':'Delivered','recipients':[{'phoneNumber':'0702222222'}],
    'textMessage':{'text':'Outgoing from gateway with no SIM'},
    'states':{'Sent':'2026-10-08T12:02:00+02:00'}
})
window._refresh_view()
assert window.list.count()==1, 'Unknown-SIM outgoing must attach to the same selected-SIM conversation'
thread=window.conversation_data['46702222222']
assert len(thread)==3, thread
assert any(m['direction']=='outgoing' and m['sim'] is None for m in thread), 'Must not invent SIM for gateway outgoing'
assert window.table.rowCount()==1, 'Sent archive must show unknown-SIM outgoing'
assert 'unknown' in window.table.item(0,4).text().lower()
# Disable the outgoing exception in Settings, while incoming SIM selection remains strict.
window.unassigned_sent.setChecked(False)
window.save_settings()
assert len(window.conversation_data['46702222222'])==2
assert window.table.rowCount()==0
window.unassigned_sent.setChecked(True)
window.save_settings()
assert len(window.conversation_data['46702222222'])==3
assert window.table.rowCount()==1

# Native notifications: simulated only, never contact SMSGate or send SMS.
window.notify_toggle.setChecked(True)
window.notify_preview.setChecked(False)
window.close_to_tray.setChecked(True)
window.save_settings()
assert window.settings['desktop_notifications'] is True
assert window.settings['notification_preview'] is False
assert window.settings['close_to_tray'] is True

# Auto-start: registry simulated, without touching any actual Windows login settings.
window.start_with_windows.setChecked(True)
window.save_settings()
assert window.settings['start_with_windows'] is True
assert _fake_startup['command'] is not None and '--background' in _fake_startup['command']
window.start_with_windows.setChecked(False)
window.save_settings()
assert window.settings['start_with_windows'] is False
assert _fake_startup['command'] is None

# Password storage: explicit opt-in, tracked as persisted, without touching WinCred.
window.secret.setText('GUI-test-only-secret')
window.remember.setChecked(True)
window.save_settings()
assert _fake_credentials.get(window.settings['url']) == 'GUI-test-only-secret'
assert window.settings['remember_password'] is True
assert window.secret.text() == ''
assert 'Saved in Windows Credential Manager' in window.password_status.text()

# Arrival notifications: baseline is quiet; selected SIM alerts only once.
window._notification_tracker.ingest([],window.sim)
window._sync_complete({'health':{'status':'pass','version':'test'},'inbox':[], 'sent':None,'errors':{}})
from unittest.mock import patch as mock_patch
with mock_patch.object(window, '_show_notification', return_value=True) as alert_mock:
    window._sync_complete({'health':{'status':'pass'},'inbox':[
       {'id':'notice-1','createdAt':'2026-10-08T13:00:00+02:00', 'sender':'+46701111111','simNumber':1,'contentPreview':'Different SIM'},
       {'id':'notice-2','createdAt':'2026-10-08T13:01:00+02:00', 'sender':'+46702222222','simNumber':2,'contentPreview':'Correct SIM'}], 'sent':None,'errors':{}})
    assert alert_mock.call_count == 1, 'Only selected SIM must notify'
    window._sync_complete({'health':{'status':'pass'},'inbox':[
       {'id':'notice-1','createdAt':'2026-10-08T13:00:00+02:00', 'sender':'+46701111111','simNumber':1,'contentPreview':'Different SIM'},
       {'id':'notice-2','createdAt':'2026-10-08T13:01:00+02:00', 'sender':'+46702222222','simNumber':2,'contentPreview':'Correct SIM'}], 'sent':None,'errors':{}})
    assert alert_mock.call_count == 1, 'Repeated sync cannot double-notify'

# SMS templates and multiple destinations: mock all sends and confirmation.
# No real outbound SMS, server traffic or Windows credential mutations.
from PySide6.QtWidgets import QMessageBox
from unittest.mock import Mock
window._show_page(2)
window.compose.setPlainText('Din cykel är klar för hämtning.')
with patch.object(app_module.QInputDialog, 'getText', return_value=('Bike pickup', True)):
    window._save_new_template()
assert window.templates['Bike pickup'] == 'Din cykel är klar för hämtning.'
assert window.template_picker.currentText() == 'Bike pickup'
window.compose.clear()
window.template_picker.setCurrentIndex(0)
window.template_picker.setCurrentText('Bike pickup')
assert 'Din cykel' in window.compose.toPlainText()
window.compose.setPlainText('Cykeln kan hämtas idag.')
with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
    window._update_template()
assert window.templates['Bike pickup'] == 'Cykeln kan hämtas idag.'
assert window.templates_path.exists()

# One international number repeated in local format is one recipient.
window.recipient.setPlainText('0702222222, +46702222222;\n+46703333333')
assert '2 unique recipient' in window.recipient_count.text()
fake_gateway = Mock()
fake_gateway.send_many.return_value = {'id': 'batch-test-1'}
def run_without_network(task, success, fail):
    success(task())
with patch.object(window, '_gateway', return_value=fake_gateway), \
     patch.object(window, '_run', side_effect=run_without_network), \
     patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), \
     patch.object(QMessageBox, 'information'):
    window.send_compose()
fake_gateway.send_many.assert_called_once_with(
    ['+46702222222', '+46703333333'], 'Cykeln kan hämtas idag.', 2)
assert len([x for x in window.cache['local_sent'] if x['id'] == 'batch-test-1']) == 2
assert window.recipient.toPlainText() == ''
assert window.compose.toPlainText() == ''
# Invalid one of many: no send, preserve fields, show validation error.
window.recipient.setPlainText('+46702222222, wrong-name')
window.compose.setPlainText('Do not send')
with patch.object(window, '_show_error') as display_error:
    window.send_compose()
    display_error.assert_called_once()
fake_gateway.send_many.assert_called_once()
# Delete requires explicit approval, and affects only local templates.
with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
    window._delete_template()
assert 'Bike pickup' not in window.templates

# Regression: the Settings page must not clip controls on a compact monitor.
# Check both minimum-sized and wide windows, using the real Qt layout engine.
from PySide6.QtCore import QPoint
window._show_page(5)
window.show()
for width, height in ((900, 630), (1040, 680), (1440, 900)):
    window.resize(width, height)
    app.processEvents()
    assert window.width() <= width + 2, f"Qt forced a wider window at {width}x{height}: {window.width()}"
    area = window.settings_scroll
    viewport = area.viewport()
    page = window.settings_content
    assert area.horizontalScrollBar().maximum() == 0, f'Horizontal scrolling at {width}x{height}'
    assert page.width() <= viewport.width() + 2, f'Settings exceed viewport at {width}x{height}'
    assert viewport.width() >= 300, f'Settings viewport too narrow at {width}x{height}'
    # Text inputs and selects must fit inside their own card, no clipped right edge.
    for widget in (window.url, window.username, window.secret, window.selected_sim,
                   window.theme_select, window.interval):
        position = widget.mapTo(page, QPoint(0, 0))
        assert position.x() >= 0, f'{widget.objectName()} starts offscreen'
        assert position.x() + widget.width() <= page.width() + 2, \
            f'{widget.__class__.__name__} extends beyond Settings width at {width}x{height}'
    # Save must always be visible, regardless of scroll position.
    button = window.settings_save_button
    saved_pos = button.mapTo(window.stack, QPoint(0, 0))
    assert button.isVisible(), f'Save settings hidden at {width}x{height}'
    assert saved_pos.y() + button.height() <= window.stack.height() + 2, \
        f'Save settings clipped below window at {width}x{height}'
    assert saved_pos.x() + button.width() <= window.stack.width() + 2, \
        f'Save settings clipped horizontally at {width}x{height}'
    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
    app.processEvents()
    assert button.isVisible(), 'Save button should remain visible after scrolling'

# Optional authentic, privacy-safe UI screenshots for GitHub documentation.
# Uses this actual PySide6 window with synthetic 555-01xx demonstration numbers.
screenshot_dir = os.environ.get('SMSGATE_SCREENSHOT_DIR')
if screenshot_dir:
    from pathlib import Path
    from core import normalize_sent
    target = Path(screenshot_dir)
    target.mkdir(parents=True, exist_ok=True)
    window.search.clear()
    window.search_delay.stop()
    window.country_code.setText('1')
    window.selected_sim.setCurrentIndex(0)
    window.remember.setChecked(False)
    window.url.setText('http://192.168.1.10:8080')
    window.username.setText('demo')
    # Changing the account requires a new password; the mock value is never
    # saved, used for real networking or displayed in screenshots.
    window.secret.setText('synthetic-screenshot-password')
    window.save_settings()
    window.secret.clear()
    window.cache['inbox'] = [
        {'id':'demo-in-1','phone':'+12025550101','date':'2026-10-12T09:20:00+02:00',
         'sim':1,'text':'Hi! Is my bicycle ready?','direction':'incoming','state':'SMS'},
        {'id':'demo-in-2','phone':'+12025550101','date':'2026-10-12T09:25:00+02:00',
         'sim':1,'text':'Thanks, see you soon!','direction':'incoming','state':'SMS'},
        {'id':'demo-in-3','phone':'+12025550102','date':'2026-10-12T10:30:00+02:00',
         'sim':1,'text':'Can I book a service for Friday?','direction':'incoming','state':'SMS'},
    ]
    window.cache['sent'] = normalize_sent({
        'id':'demo-out-1','state':'Delivered',
        'recipients':[{'phoneNumber':'+12025550101'}],
        'textMessage':{'text':'Your bicycle is ready for pickup.'},
        'states':{'Sent':'2026-10-12T09:22:00+02:00'}
    })
    window.cache['local_sent'] = []
    window._current_signature = None
    # Show the multi-message 555-0101 demo conversation rather than the
    # most recent one-message thread in the public screenshot.
    window.active_key = '12025550101'
    window._refresh_view()
    window._show_page(0)
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    assert window.grab().save(str(target / 'conversations.png')), 'Conversations screenshot failed'
    window._show_page(5)
    window.resize(1280, 850)
    window.settings_scroll.verticalScrollBar().setValue(0)
    app.processEvents()
    assert window.grab().save(str(target / 'settings.png')), 'Settings screenshot failed'
    print('Captured authentic Qt screenshots with synthetic numbers; no gateway used.')

# Changes made to Settings do not turn into sends, and no POST is issued in this smoke test.
window._closing=True
window.close()
app.processEvents()
import faulthandler
from app import CRASH_STREAM
faulthandler.disable()
CRASH_STREAM.close()
import logging
logging.shutdown()  # Release log handles before Windows removes test directory.
tmp.cleanup()
for patched in (startup_cmd, startup_restore, startup_write, startup_read, sync_patch, delete_patch, write_patch, read_patch):
    patched.stop()
print('GUI smoke PASS: auto-start toggle, SIM isolation, theme, outgoing messages, Settings responsiveness')
