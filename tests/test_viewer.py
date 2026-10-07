import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings, Qt, QPoint, QPointF
from PySide6.QtGui import QPdfWriter, QPainter, QColor, QImage, QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app import MainWindow, filtered_image
from settings_store import open_settings

APP = QApplication.instance() or QApplication([])


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.pdf = root / "sample.pdf"
        writer = QPdfWriter(str(self.pdf))
        painter = QPainter(writer)
        for page in range(5):
            if page:
                writer.newPage()
            painter.fillRect(100, 100, 400, 400, QColor("#7e93ee"))
            painter.drawText(100, 600, f"B01PDF page {page + 1}")
        painter.end()
        del painter
        del writer
        self.settings = open_settings(root, QSettings(str(root / "legacy.ini"), QSettings.Format.IniFormat))
        self.window = MainWindow(self.settings)
        self.window.show()
        APP.processEvents()
        self.assertTrue(self.window.open_file(str(self.pdf)))
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        APP.processEvents()
        from shiboken6 import delete
        delete(self.window)
        self.temp.cleanup()

    def test_changes_stay_in_memory_until_one_exit_flush(self):
        from unittest.mock import patch
        path = Path(self.settings.fileName())
        before = path.read_bytes()
        stamp = path.stat().st_mtime_ns
        other_pdf = Path(self.temp.name) / "other.pdf"
        other_pdf.write_bytes(self.pdf.read_bytes())
        with patch.object(self.settings, "sync", wraps=self.settings.sync) as sync:
            self.window.set_zoom(200)
            self.window.set_fit("page")
            self.window.theme_action.setChecked(True)
            self.window.go_to(3)
            QTest.qWait(600)  # Let the reading-position timer run.
            self.assertTrue(self.window.open_file(str(other_pdf)))
            self.window.go_to(1)
            QTest.qWait(600)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.stat().st_mtime_ns, stamp)
            sync.assert_not_called()
            self.window.close()
            self.window.flush_settings_on_exit()  # aboutToQuit must not flush twice.
            sync.assert_called_once()
        reopened = open_settings(Path(self.temp.name))
        self.assertEqual(reopened.value("view/fit"), "page")
        self.assertTrue(reopened.value("view/dark", type=bool))
        import hashlib, json
        for pdf, page in ((self.pdf, 3), (other_pdf, 1)):
            key = "positions/" + hashlib.sha256(str(pdf.resolve()).encode("utf-8")).hexdigest()
            self.assertEqual(json.loads(reopened.value(key))["page"], page)
        self.assertTrue(reopened.contains("geometry"))

    def test_render_and_zoom(self):
        self.assertEqual(self.window.document.pageCount(), 5)
        self.window.set_zoom(100)
        rect = self.window.viewer.pages.rectangles[0][1]
        size = self.window.document.pagePointSize(0)
        self.assertAlmostEqual(rect.width(), size.width() * 96 / 72, delta=1)
        self.window.set_zoom(200)
        self.assertGreater(self.window.viewer.pages.rectangles[0][1].width(), rect.width())
        self.window.set_fit("width")
        APP.processEvents()
        self.assertLessEqual(self.window.viewer.pages.rectangles[0][1].width(), self.window.viewer.viewport().width())
        self.window.set_fit("page")
        self.assertLessEqual(self.window.viewer.pages.rectangles[0][1].height(), self.window.viewer.viewport().height())
        self.assertFalse(self.window.document.render(0, rect.size()).isNull())

    def test_modes_and_last_odd_page(self):
        self.window.change_mode(1)
        self.assertEqual([p for p, _ in self.window.viewer.pages.rectangles], [0, 1])
        self.window.go_to(4)
        self.assertEqual([p for p, _ in self.window.viewer.pages.rectangles], [4])
        self.window.change_mode(2)
        self.assertEqual(len(self.window.viewer.pages.rectangles), 5)
        self.window.go_to(3)
        self.assertEqual(self.window.page, 3)
        self.assertEqual(len(self.window.sidebar.pages.rectangles), 5)

    def test_remember_page_and_scroll_offset(self):
        self.window.change_mode(2)
        self.window.go_to(2)
        rect = self.window.viewer.pages.rectangles[2][1]
        self.window.viewer.verticalScrollBar().setValue(rect.top() + rect.height() // 3)
        APP.processEvents()
        saved = self.window.viewer.verticalScrollBar().value()
        self.window.save_position()
        self.assertTrue(self.window.open_file(str(self.pdf)))
        self.assertEqual(self.window.page, 2)
        self.assertEqual(self.window.view_mode, "scroll")
        self.assertAlmostEqual(self.window.viewer.verticalScrollBar().value(), saved, delta=2)
        self.settings.setValue("remember", False)
        self.assertTrue(self.window.open_file(str(self.pdf)))
        self.assertEqual(self.window.page, 0)

    def test_filter_changes_pixels_and_cache_bounded(self):
        image = QImage(32, 32, QImage.Format.Format_RGBA8888)
        image.fill(QColor("#888888"))
        painter = QPainter(image)
        painter.fillRect(16, 0, 16, 32, QColor("#bbbbbb"))
        painter.end()
        sharp = filtered_image(image, "sharp")
        self.assertNotEqual(bytes(image.constBits()), bytes(sharp.constBits()))
        for index in range(2):
            self.window.change_filter(index)
            self.window.viewer.pages.grab()
        self.assertLessEqual(self.window.cache.bytes, self.window.cache.limit)

    def test_arrow_home_end_and_wheel_navigation(self):
        for mode in (0, 1):
            self.window.change_mode(mode)
            self.window.go_to(0)
            step = 1 if mode == 0 else 2
            for key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
                self.window.go_to(0)
                QTest.keyClick(self.window.viewer, key)
                self.assertEqual(self.window.page, step)
            for key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
                self.window.go_to(step)
                QTest.keyClick(self.window.viewer, key)
                self.assertEqual(self.window.page, 0)
            QTest.keyClick(self.window.viewer, Qt.Key.Key_End)
            self.assertEqual(self.window.page, 4)
            QTest.keyClick(self.window.viewer, Qt.Key.Key_Home)
            self.assertEqual(self.window.page, 0)
            self.window.set_fit("page")
            for delta, expected in ((-120, step), (120, 0)):
                event = QWheelEvent(QPointF(30, 30), QPointF(30, 30), QPoint(), QPoint(0, delta),
                                    Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                    Qt.ScrollPhase.NoScrollPhase, False)
                self.window.viewer.wheelEvent(event)
                self.assertEqual(self.window.page, expected)

    def test_global_preferences_across_files_and_restart(self):
        self.window.change_mode(1)
        self.window.set_fit("page")
        self.window.change_filter(1)
        self.window.theme_action.setChecked(True)
        self.window.sidebar_action.setChecked(False)
        other_pdf = Path(self.temp.name) / "other.pdf"
        other_pdf.write_bytes(self.pdf.read_bytes())
        self.assertTrue(self.window.open_file(str(other_pdf)))
        self.assertEqual((self.window.view_mode, self.window.fit), ("two", "page"))
        self.window.close()
        from shiboken6 import delete
        delete(self.window)
        self.window = MainWindow(self.settings)
        self.window.show()
        APP.processEvents()
        self.assertTrue(self.window.open_file(str(self.pdf)))
        self.assertEqual((self.window.view_mode, self.window.fit, self.window.filter_mode), ("two", "page", "sharp"))
        self.assertTrue(self.window.dark_mode)
        self.assertFalse(self.window.sidebar.isVisible())
        self.window.change_mode(2)
        self.window.set_fit("width")
        self.assertTrue(self.window.open_file(str(other_pdf)))
        self.assertEqual((self.window.view_mode, self.window.fit), ("scroll", "width"))


    def wheel(self, delta, modifiers=Qt.KeyboardModifier.NoModifier):
        event = QWheelEvent(QPointF(30, 30), QPointF(30, 30), QPoint(), QPoint(0, delta),
                            Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
        self.window.viewer.wheelEvent(event)

    def test_fit_button_states_and_theme_icons(self):
        self.window.fit_width_action.trigger()
        self.assertEqual(self.window.fit, "width")
        self.assertTrue(self.window.fit_width_action.isChecked())
        self.assertFalse(self.window.fit_page_action.isChecked())
        self.window.fit_page_action.trigger()
        self.assertFalse(self.window.fit_width_action.isChecked())
        self.assertTrue(self.window.fit_page_action.isChecked())
        self.window.fit_page_action.trigger()
        self.assertTrue(self.window.fit_page_action.isChecked())
        self.window.set_zoom(100)
        self.assertFalse(self.window.fit_page_action.isChecked())
        self.assertFalse(self.window.fit_width_action.isChecked())
        self.window.theme_action.setChecked(True)
        self.assertEqual(self.window.theme_action.text(), "Dark")
        dark_icon = self.window.theme_action.icon().cacheKey()
        self.window.theme_action.trigger()
        self.assertFalse(self.window.dark_mode)
        self.assertEqual(self.window.theme_action.text(), "Light")
        self.assertNotEqual(self.window.theme_action.icon().cacheKey(), dark_icon)
        self.window.theme_action.trigger()
        self.assertTrue(self.window.dark_mode)
        self.assertIs(self.window.theme_button.defaultAction(), self.window.theme_action)
        self.assertEqual(APP.font().family(), "Malgun Gothic")
        self.assertEqual(self.window.toolbar.actions()[0], self.window.sidebar_action)
        for action in (self.window.sidebar_action, self.window.open_action,
                       self.window.theme_action):
            self.assertFalse(action.icon().isNull())
            self.assertEqual((self.window.theme_button if action is self.window.theme_action else self.window.toolbar.widgetForAction(action)).toolButtonStyle(),
                             Qt.ToolButtonStyle.ToolButtonIconOnly)

    def test_theme_button_geometry_is_stable_across_themes_and_widths(self):
        button = self.window.theme_button
        for width in (800, 1120, 1500):
            self.window.resize(width, 800)
            QTest.qWait(20)
            previous = None
            for dark in (False, True, False, True):
                self.window.apply_theme(dark)
                QTest.qWait(20)
                geometry = button.geometry()
                self.assertEqual((button.width(), button.height()), (32, 32))
                for action in (self.window.fit_width_action, self.window.fit_page_action,
                               self.window.shortcut_actions["Settings"], self.window.shortcut_actions["100%"]):
                    self.assertEqual(self.window.toolbar.widgetForAction(action).height(), 32)
                self.assertTrue(button.isVisible())
                self.assertEqual(self.window.toolbar_divider.width(), self.window.width())
                right = button.mapTo(self.window, QPoint(button.width(), 0)).x()
                self.assertEqual(self.window.width() - right, 6)
                sidebar = self.window.toolbar.widgetForAction(self.window.sidebar_action)
                button_y = button.mapTo(self.window, QPoint(0, button.height() // 2)).y()
                sidebar_y = sidebar.mapTo(self.window, QPoint(0, sidebar.height() // 2)).y()
                self.assertLessEqual(abs(button_y - sidebar_y), 1)
                if previous is not None:
                    self.assertEqual(geometry, previous)
                previous = geometry

    def test_double_click_opens_only_when_document_is_empty(self):
        from unittest.mock import patch
        with patch.object(self.window, "choose_file") as choose:
            QTest.mouseDClick(self.window.viewer.pages, Qt.MouseButton.LeftButton)
            choose.assert_not_called()
            self.window.document.close()
            self.window.relayout()
            APP.processEvents()
            for surface in (self.window.viewer.viewport(), self.window.viewer.pages,
                            self.window.sidebar.viewport(), self.window.sidebar.pages):
                choose.reset_mock()
                QTest.mouseDClick(surface, Qt.MouseButton.LeftButton)
                choose.assert_called_once()

    def test_oversized_page_scroll_boundary_and_horizontal_pan(self):
        for mode in (0, 1):
            self.window.change_mode(mode)
            self.window.go_to(0)
            self.window.set_zoom(200)
            APP.processEvents()
            vertical = self.window.viewer.verticalScrollBar()
            horizontal = self.window.viewer.horizontalScrollBar()
            self.assertGreater(vertical.maximum(), 0)
            self.assertGreater(horizontal.maximum(), 0)
            self.wheel(-120)
            self.assertGreater(vertical.value(), 0)
            self.assertEqual(self.window.page, 0)
            vertical.setValue(vertical.maximum())
            self.wheel(-120)
            self.assertEqual(self.window.page, 1 if mode == 0 else 2)
            self.assertLess(vertical.value(), vertical.maximum())
            vertical.setValue(0)
            self.wheel(120)
            self.assertEqual(self.window.page, 0)
            self.assertEqual(vertical.value(), vertical.maximum())
            self.window.go_to(4)
            vertical.setValue(vertical.maximum())
            last_bottom = vertical.value()
            self.wheel(-120)
            self.assertEqual(self.window.page, 4)
            self.assertEqual(vertical.value(), last_bottom)
            self.window.go_to(0)
            horizontal.setValue(0)
            self.wheel(-120, Qt.KeyboardModifier.ShiftModifier)
            self.assertGreater(horizontal.value(), 0)
            self.assertEqual(self.window.page, 0)
            horizontal.setValue(horizontal.maximum())
            self.wheel(-120, Qt.KeyboardModifier.ShiftModifier)
            self.assertEqual(self.window.page, 0)
            horizontal.setValue(100)
            vertical.setValue(100)
            self.window.viewer.begin_pan(QPointF(200, 200))
            self.window.viewer.move_pan(QPointF(150, 130))
            self.window.viewer.end_pan()
            self.assertEqual(horizontal.value(), 150)
            self.assertEqual(vertical.value(), 170)
            self.assertEqual(self.window.page, 0)

    def test_thumbnail_scales_with_sidebar_width(self):
        self.window.splitter.setSizes([165, 955])
        APP.processEvents()
        self.window.relayout()
        small = self.window.sidebar.pages.rectangles[0][1].width()
        self.window.splitter.setSizes([350, 770])
        APP.processEvents()
        self.window.relayout()
        large = self.window.sidebar.pages.rectangles[0][1].width()
        self.assertGreater(large, small)
        self.assertLessEqual(large + 40, self.window.sidebar.viewport().width())
        self.assertEqual(self.window.sidebar.horizontalScrollBar().maximum(), 0)


    def test_zoom_presets_and_ctrl_wheel(self):
        levels = [10, 25, 33, 50, 75, 100, 150, 200, 300]
        self.window.set_zoom(10)
        self.window.step_zoom(-1)
        self.assertEqual(self.window.zoom, 10)
        for level in levels[1:]:
            self.window.shortcut_actions["Zoom In"].trigger()
            self.assertEqual(self.window.zoom, level)
        self.window.step_zoom(1)
        self.assertEqual(self.window.zoom, 300)
        for level in reversed(levels[:-1]):
            self.window.shortcut_actions["Zoom Out"].trigger()
            self.assertEqual(self.window.zoom, level)
        self.window.set_zoom(110)
        self.window.step_zoom(1)
        self.assertEqual(self.window.zoom, 150)
        self.wheel(-120, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.zoom, 140)
        self.wheel(120, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.zoom, 150)

    def test_requested_shortcuts_and_title(self):
        self.assertEqual(self.window.windowTitle(), "B01PDF")
        expected = {"Fit Page": "Ctrl+0", "Fit Width": "Ctrl+9", "100%": "Ctrl+1",
                    "200%": "Ctrl+2", "300%": "Ctrl+3", "50%": "Ctrl+`",
                    "Zoom In": "Ctrl++", "Zoom Out": "Ctrl+-", "Open": "Ctrl+O",
                    "Settings": "Ctrl+,", "1 Page": "Alt+1", "2 Pages": "Alt+2",
                    "Scroll": "Alt+3", "Quit": "Ctrl+Q"}
        for name, shortcut in expected.items():
            self.assertEqual(self.window.shortcut_actions[name].shortcut().toString(), shortcut)
        self.window.activateWindow()
        self.window.viewer.setFocus()
        APP.processEvents()
        QTest.keyClick(self.window.viewer, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.fit, "page")
        QTest.keyClick(self.window.viewer, Qt.Key.Key_9, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.fit, "width")
        for key, value in [(Qt.Key.Key_1, 100), (Qt.Key.Key_2, 200), (Qt.Key.Key_3, 300), (Qt.Key.Key_QuoteLeft, 50)]:
            QTest.keyClick(self.window.viewer, key, Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(self.window.zoom, value)
        for key, mode in [(Qt.Key.Key_1, "single"), (Qt.Key.Key_2, "two"), (Qt.Key.Key_3, "scroll")]:
            QTest.keyClick(self.window.viewer, key, Qt.KeyboardModifier.AltModifier)
            self.assertEqual(self.window.view_mode, mode)
        self.settings.setValue("shortcuts/200%", "Ctrl+8")
        self.window.apply_shortcuts()
        self.window.set_zoom(100)
        QTest.keyClick(self.window.viewer, Qt.Key.Key_8, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.zoom, 200)

    def test_quit_confirmation_and_sidebar_limit(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel), patch.object(self.window, "close") as close:
            self.window.shortcut_actions["Quit"].trigger()
            close.assert_not_called()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Ok), patch.object(self.window, "close") as close:
            self.window.shortcut_actions["Quit"].trigger()
            close.assert_called_once()
        for width in (800, 1000, 1100, 1120, 1500, 1600):
            self.window.resize(width, 800)
            self.window.splitter.setSizes([10000, 200])
            APP.processEvents()
            self.assertGreaterEqual(self.window.sidebar.width(), 160)
            self.assertEqual(self.window.sidebar.maximumWidth(), min(220, width // 5))
            self.assertLessEqual(self.window.sidebar.width(), min(220, width // 5))
            self.window.splitter.setSizes([0, width])
            APP.processEvents()
            self.assertGreaterEqual(self.window.sidebar.width(), 160)


    def test_shortcut_editor_saves_and_rejects_conflicts(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QDialog, QKeySequenceEdit, QDialogButtonBox, QMessageBox
        from PySide6.QtGui import QKeySequence
        def edit(dialog):
            editors = dialog.findChildren(QKeySequenceEdit)
            index = list(self.window.shortcut_actions).index("200%")
            editor = editors[index]
            buttons = dialog.findChild(QDialogButtonBox)
            editor.setKeySequence(QKeySequence("Ctrl+1"))
            with patch.object(QMessageBox, "warning") as warning:
                buttons.button(QDialogButtonBox.StandardButton.Ok).click()
                warning.assert_called_once()
            self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
            editor.setKeySequence(QKeySequence("Ctrl+8"))
            buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            return dialog.result()
        with patch.object(QDialog, "exec", edit):
            self.window.show_settings()
        self.assertEqual(self.settings.value("shortcuts/200%"), "Ctrl+8")
        self.assertEqual(self.window.shortcut_actions["200%"].shortcut().toString(), "Ctrl+8")



if __name__ == "__main__":
    unittest.main()
