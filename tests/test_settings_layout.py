"""Static regression assertions; GUI sizing is also checked in gui_smoke on Windows."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / 'app.py').read_text(encoding='utf-8')


class SettingsLayoutTests(unittest.TestCase):
    def test_settings_has_scroller_and_sticky_save(self):
        self.assertIn('self.settings_scroll = QScrollArea()', APP)
        self.assertIn('self.settings_scroll.setWidgetResizable(True)', APP)
        self.assertIn('ScrollBarAlwaysOff', APP)
        self.assertIn('self.settings_save_button', APP)
        self.assertIn('v.addWidget(self.settings_scroll, 1)', APP)
        self.assertIn('v.addWidget(footer, 0)', APP)
        self.assertLess(APP.index('v.addWidget(self.settings_scroll, 1)'), APP.index('v.addWidget(footer, 0)'))

    def test_settings_have_all_original_controls(self):
        ast.parse(APP)
        expected = ('url','username','secret','remember','password_status','selected_sim',
                    'country_code','unknown','unassigned_sent','theme_select','interval','notify_toggle',
                    'notify_preview','close_to_tray','start_with_windows','startup_status')
        start = APP.index('    def _build_settings(self):')
        end = APP.index('    def _setup_tray(self):', start)
        block = APP[start:end]
        for name in expected:
            with self.subTest(name=name):
                self.assertIn('self.'+name+' =',block)


    def test_login_startup_is_tray_first_with_visible_fallback(self):
        self.assertIn('background_launch = BACKGROUND_FLAG in sys.argv', APP)
        self.assertIn('if background_launch and tray_ready:', APP)
        self.assertIn('app.setQuitOnLastWindowClosed(False)', APP)
        self.assertIn('window.show()', APP)
        self.assertIn("'start_with_windows':desired_startup", APP)
        self.assertIn('restore_startup(previous_command)', APP)

    def test_gui_test_checks_three_sizes(self):
        smoke = (ROOT / 'tests' / 'gui_smoke.py').read_text(encoding='utf-8')
        self.assertIn('(900, 630), (1040, 680), (1440, 900)',smoke)
        self.assertIn('window.settings_save_button',smoke)
        self.assertIn('horizontalScrollBar().maximum()',smoke)


if __name__ == '__main__':
    unittest.main()
