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
        self.settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
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

    def test_fit_button_states_and_theme_label(self):
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
        self.window.theme_action.setChecked(False)
        self.assertEqual(self.window.theme_action.text(), "Light")

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



if __name__ == "__main__":
    unittest.main()
