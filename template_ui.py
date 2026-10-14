"""Local, opt-in SMS template editing for the desktop compose screen.

Templates contain message text only. Recipients and passwords are never stored
in templates, and selecting a template can never send an SMS.
"""
from PySide6.QtWidgets import QInputDialog, QMessageBox

from core import MAX_RECIPIENTS, MAX_TEMPLATES, json_save, parse_recipients, validate_template


class TemplateMixin:
    def _update_recipient_count(self):
        raw = self.recipient.toPlainText()
        if not raw.strip():
            info = f'No recipients yet (max {MAX_RECIPIENTS})'
        else:
            try:
                numbers = parse_recipients(raw, self.settings['country_code'])
                info = f'{len(numbers)} unique recipient(s) · maximum {MAX_RECIPIENTS}'
            except ValueError as exc:
                info = str(exc)
        self.recipient_count.setText(info)

    def _refresh_template_picker(self, selected=''):
        self.template_picker.blockSignals(True)
        try:
            self.template_picker.clear()
            self.template_picker.addItem('Choose a saved template…')
            for name in sorted(self.templates, key=str.casefold):
                self.template_picker.addItem(name)
            self.template_picker.setCurrentIndex(max(0, self.template_picker.findText(selected)))
        finally:
            self.template_picker.blockSignals(False)

    def _apply_template(self, index):
        if index > 0:
            # Never send or change recipients when loading a template.
            self.compose.setPlainText(self.templates[self.template_picker.itemText(index)])

    def _save_new_template(self):
        name, ok = QInputDialog.getText(self, 'Save SMS template', 'Template name:')
        if not ok:
            return
        try:
            name, body = validate_template(name, self.compose.toPlainText())
            if any(k.casefold() == name.casefold() for k in self.templates):
                raise ValueError('That template exists. Select it and click Update.')
            if len(self.templates) >= MAX_TEMPLATES:
                raise ValueError(f'Maximum {MAX_TEMPLATES} saved templates.')
            updated = dict(self.templates)
            updated[name] = body
            json_save(self.templates_path, updated)
            self.templates = updated
            self._refresh_template_picker(name)
        except (ValueError, OSError) as exc:
            self._show_error(str(exc))

    def _update_template(self):
        name = self.template_picker.currentText()
        if name not in self.templates:
            return self._show_error('Select an existing template to update.')
        try:
            _, body = validate_template(name, self.compose.toPlainText())
        except ValueError as exc:
            return self._show_error(str(exc))
        if QMessageBox.question(
            self, 'Update template', f'Overwrite template "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            updated = dict(self.templates)
            updated[name] = body
            json_save(self.templates_path, updated)
            self.templates = updated
        except OSError as exc:
            self._show_error(str(exc))

    def _delete_template(self):
        name = self.template_picker.currentText()
        if name not in self.templates:
            return self._show_error('Select an existing template to delete.')
        if QMessageBox.question(
            self, 'Delete template', f'Delete template "{name}" permanently?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            updated = dict(self.templates)
            del updated[name]
            json_save(self.templates_path, updated)
            self.templates = updated
            self._refresh_template_picker()
        except OSError as exc:
            self._show_error(str(exc))
