import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings
from PySide6.QtGui import QPdfWriter, QPainter, QColor, QImage
from PySide6.QtWidgets import QApplication
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
        for index in range(3):
            self.window.change_filter(index)
            self.window.viewer.pages.grab()
        self.assertLessEqual(self.window.cache.bytes, self.window.cache.limit)


if __name__ == "__main__":
    unittest.main()
