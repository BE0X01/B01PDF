"""B01PDF: local-only, minimal desktop PDF viewer."""
import hashlib
import json
import sys
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageFilter
from PySide6.QtCore import Qt, QSize, QRect, QSettings, QTimer, Signal
from PySide6.QtGui import QAction, QImage, QPainter, QColor, QKeySequence
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QScrollArea, QSplitter, QToolBar,
    QPushButton, QLabel, QComboBox, QSpinBox, QFileDialog, QMessageBox,
    QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QInputDialog, QLineEdit,
)


def filtered_image(image, mode):
    if mode != "sharp":
        return image
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    pil = Image.frombytes("RGBA", (rgba.width(), rgba.height()), bytes(rgba.constBits()),
                          "raw", "RGBA", rgba.bytesPerLine())
    result = pil.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=3))
    data = result.tobytes()
    return QImage(data, result.width, result.height, result.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


class ImageCache:
    """Bounded in-memory render cache; never renders the whole PDF eagerly."""
    def __init__(self, document, limit=96 * 1024 * 1024):
        self.document = document
        self.limit = limit
        self.images = OrderedDict()
        self.bytes = 0

    def clear(self):
        self.images.clear()
        self.bytes = 0

    def get(self, page, size, mode="original"):
        key = (page, size.width(), size.height(), mode)
        if key in self.images:
            self.images.move_to_end(key)
            return self.images[key]
        image = filtered_image(self.document.render(page, size), mode)
        if image.isNull():
            return image
        cost = image.sizeInBytes()
        while self.images and self.bytes + cost > self.limit:
            _, old = self.images.popitem(last=False)
            self.bytes -= old.sizeInBytes()
        if cost <= self.limit:
            self.images[key] = image
            self.bytes += cost
        return image


class Pages(QWidget):
    pageChanged = Signal(int)

    def __init__(self, window, thumbnails=False):
        super().__init__()
        self.window = window
        self.thumbnails = thumbnails
        self.rectangles = []
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor("#e9e9ed" if thumbnails else "#d9dbe1"))
        self.setPalette(palette)

    def layout_pages(self):
        w = self.window
        count = w.document.pageCount()
        if not count:
            self.rectangles = []
            self.resize(max(1, self.parent().width()), max(1, self.parent().height()))
            self.update()
            return
        viewport = self.parent()
        available_w, available_h = max(100, viewport.width()), max(100, viewport.height())
        if self.thumbnails:
            rows = [[p] for p in range(count)]
            scale = 110 / max(w.document.pagePointSize(p).width() for p in range(count))
        else:
            if w.view_mode == "scroll":
                rows = [[p] for p in range(count)]
            elif w.view_mode == "two":
                first = (w.page // 2) * 2
                rows = [list(range(first, min(first + 2, count)))]
            else:
                rows = [[w.page]]
            scale = w.zoom / 100 * 96 / 72
            if w.fit != "manual":
                fit_rows = rows if w.view_mode != "scroll" else [[w.page]]
                width = max(sum(w.document.pagePointSize(p).width() for p in row)
                            for row in fit_rows)
                gap = 18 if w.view_mode == "two" and len(rows[0]) == 2 else 0
                scale = max(.05, (available_w - 40 - gap) / width)
                if w.fit == "page":
                    height = max(w.document.pagePointSize(p).height() for row in fit_rows for p in row)
                    scale = min(scale, max(.05, (available_h - 40) / height))
                w.show_zoom(scale * 72 / 96 * 100)
        row_sizes = []
        for row in rows:
            sizes = [(p, max(1, round(w.document.pagePointSize(p).width() * scale)),
                      max(1, round(w.document.pagePointSize(p).height() * scale))) for p in row]
            row_sizes.append(sizes)
        content_width = max(available_w, max(sum(s[1] for s in row) + 18 * (len(row) - 1)
                                           for row in row_sizes) + 40)
        y = 20
        self.rectangles = []
        for row in row_sizes:
            row_width = sum(s[1] for s in row) + 18 * (len(row) - 1)
            x = (content_width - row_width) // 2
            for page, width, height in row:
                self.rectangles.append((page, QRect(x, y, width, height)))
                x += width + 18
            y += max(s[2] for s in row) + (34 if self.thumbnails else 20)
        self.resize(content_width, max(available_h, y))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        w = self.window
        for page, rect in self.rectangles:
            if not rect.adjusted(-5, -5, 5, 24).intersects(event.rect()):
                continue
            painter.fillRect(rect.adjusted(-1, -1, 1, 1), QColor("#babdc6"))
            painter.fillRect(rect, Qt.GlobalColor.white)
            ratio = self.devicePixelRatioF()
            factor = 1 if self.thumbnails or w.filter_mode != "smooth" else 1.5
            # Cap a render to 12 megapixels to bound individual allocations.
            rw, rh = max(1, int(rect.width() * ratio * factor)), max(1, int(rect.height() * ratio * factor))
            cap = min(1.0, (12_000_000 / (rw * rh)) ** .5)
            image = w.cache.get(page, QSize(max(1, int(rw * cap)), max(1, int(rh * cap))),
                                "original" if self.thumbnails else w.filter_mode)
            if not image.isNull():
                painter.drawImage(rect, image)
            if self.thumbnails:
                if page == w.page:
                    painter.setPen(QColor("#5468e7"))
                    painter.drawRect(rect.adjusted(-3, -3, 3, 3))
                painter.setPen(QColor("#444653"))
                painter.drawText(QRect(rect.x(), rect.bottom() + 6, rect.width(), 20),
                                 Qt.AlignmentFlag.AlignCenter, str(page + 1))

    def mousePressEvent(self, event):
        if self.thumbnails:
            for page, rect in self.rectangles:
                if rect.adjusted(-5, -5, 5, 24).contains(event.position().toPoint()):
                    self.window.go_to(page)
                    break
        super().mousePressEvent(event)


class Viewer(QScrollArea):
    def __init__(self, window, thumbnails=False):
        super().__init__()
        self.window = window
        self.thumbnails = thumbnails
        self.setWidgetResizable(False)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.pages = Pages(window, thumbnails)
        self.setWidget(self.pages)
        self.verticalScrollBar().valueChanged.connect(self.scrolled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self.window, "viewer"):
            self.window.relayout(preserve=True)

    def scrolled(self):
        w = self.window
        if self.thumbnails or w.relayouting or w.view_mode != "scroll":
            return
        top = self.verticalScrollBar().value()
        for page, rect in self.pages.rectangles:
            if rect.bottom() >= top + 24:
                w.set_current_page(page)
                break

    def wheelEvent(self, event):
        if not self.thumbnails and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.window.set_zoom(self.window.zoom + (10 if event.angleDelta().y() > 0 else -10))
            event.accept()
        else:
            super().wheelEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings("B01", "B01PDF")
        self.document = QPdfDocument(self)
        self.cache = ImageCache(self.document)
        self.path = None
        self.page = 0
        self.zoom = 100
        self.fit = "manual"
        self.view_mode = "single"
        self.filter_mode = "original"
        self.relayouting = False
        self.setWindowTitle("B01PDF")
        self.resize(1120, 800)
        self.setMinimumSize(780, 480)
        self.setAcceptDrops(True)
        self.create_toolbar()
        self.splitter = QSplitter()
        self.sidebar = Viewer(self, True)
        self.sidebar.setMinimumWidth(145)
        self.sidebar.setMaximumWidth(260)
        self.viewer = Viewer(self)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.viewer)
        self.splitter.setSizes([165, 955])
        self.setCentralWidget(self.splitter)
        self.statusBar().showMessage("PDF를 열거나 이 창에 끌어 놓으세요")
        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save_position)
        self.viewer.verticalScrollBar().valueChanged.connect(lambda: self.save_timer.start())
        self.viewer.horizontalScrollBar().valueChanged.connect(lambda: self.save_timer.start())

    def create_toolbar(self):
        bar = QToolBar("보기")
        bar.setMovable(False)
        self.addToolBar(bar)
        def button(text, callback, shortcut=None):
            action = QAction(text, self)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            bar.addAction(action)
        button("열기", self.choose_file, "Ctrl+O")
        bar.addSeparator()
        button("‹", lambda: self.go_to(self.page - (2 if self.view_mode == "two" else 1)), "PgUp")
        self.page_input = QSpinBox()
        self.page_input.setRange(1, 1)
        self.page_input.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.page_input.setFixedWidth(55)
        self.page_input.setToolTip("페이지 번호")
        self.page_input.editingFinished.connect(lambda: self.go_to(self.page_input.value() - 1))
        bar.addWidget(self.page_input)
        self.page_total = QLabel(" / 0  ")
        bar.addWidget(self.page_total)
        button("›", lambda: self.go_to(self.page + (2 if self.view_mode == "two" else 1)), "PgDown")
        bar.addSeparator()
        button("−", lambda: self.set_zoom(self.zoom - 10), "Ctrl+-")
        self.zoom_input = QSpinBox()
        self.zoom_input.setRange(10, 400)
        self.zoom_input.setSuffix("%")
        self.zoom_input.setValue(100)
        self.zoom_input.setFixedWidth(76)
        self.zoom_input.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.zoom_input.editingFinished.connect(lambda: self.set_zoom(self.zoom_input.value()))
        bar.addWidget(self.zoom_input)
        button("+", lambda: self.set_zoom(self.zoom + 10), "Ctrl+=")
        button("100%", lambda: self.set_zoom(100), "Ctrl+0")
        button("Fit Width", lambda: self.set_fit("width"))
        button("Fit Page", lambda: self.set_fit("page"))
        bar.addSeparator()
        self.mode_input = QComboBox()
        self.mode_input.addItems(["1장 보기", "2장 보기", "스크롤 보기"])
        self.mode_input.currentIndexChanged.connect(self.change_mode)
        bar.addWidget(self.mode_input)
        self.filter_input = QComboBox()
        self.filter_input.addItems(["원본", "선명하게", "부드럽게 (AA)"])
        self.filter_input.currentIndexChanged.connect(self.change_filter)
        bar.addWidget(self.filter_input)
        button("설정", self.show_settings)
        sidebar_action = QAction("사이드바", self)
        sidebar_action.setShortcut("F9")
        sidebar_action.triggered.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        self.addAction(sidebar_action)

    def remember(self):
        return self.settings.value("remember", True, type=bool)

    def position_key(self):
        return "positions/" + hashlib.sha256(str(self.path).encode("utf-8")).hexdigest()

    def save_position(self):
        if not self.path or not self.remember() or not self.document.pageCount():
            return
        rect = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
        offset = 0 if rect is None else (self.viewer.verticalScrollBar().value() - rect.top()) / rect.height()
        state = {"page": self.page, "offset": offset, "x": self.viewer.horizontalScrollBar().value(),
                 "mode": self.view_mode, "fit": self.fit, "zoom": self.zoom}
        self.settings.setValue(self.position_key(), json.dumps(state))
        self.settings.sync()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "PDF 열기", "", "PDF (*.pdf)")
        if path:
            self.open_file(path)

    def open_file(self, path):
        self.save_position()
        # Load separately so an invalid file doesn't destroy the current document.
        document = QPdfDocument(self)
        error = document.load(str(path))
        while error == QPdfDocument.Error.IncorrectPassword:
            password, ok = QInputDialog.getText(self, "암호가 필요한 PDF", "암호", QLineEdit.EchoMode.Password)
            if not ok:
                document.deleteLater()
                return False
            document.setPassword(password)
            error = document.load(str(path))
        if error != QPdfDocument.Error.None_ or document.pageCount() == 0:
            QMessageBox.warning(self, "열기 실패", "PDF 파일을 열 수 없어요. 파일 형식이나 손상 여부를 확인해 주세요.")
            document.deleteLater()
            return False
        self.save_timer.stop()
        old = self.document
        self.document = document
        self.cache.clear()
        self.cache.document = document
        old.close()
        old.deleteLater()
        self.path = Path(path).resolve()
        self.page = 0
        self.view_mode = "single"
        self.fit = "manual"
        self.zoom = 100
        state = {}
        if self.remember():
            try:
                state = json.loads(self.settings.value(self.position_key(), "{}"))
                self.page = max(0, min(document.pageCount() - 1, int(state.get("page", 0))))
                self.view_mode = state.get("mode", "single")
                if self.view_mode not in ("single", "two", "scroll"):
                    self.view_mode = "single"
                self.fit = state.get("fit", "manual")
                if self.fit not in ("manual", "width", "page"):
                    self.fit = "manual"
                self.zoom = max(10, min(400, float(state.get("zoom", 100))))
            except (ValueError, TypeError, AttributeError):
                state = {}
        self.mode_input.blockSignals(True)
        self.mode_input.setCurrentIndex(["single", "two", "scroll"].index(self.view_mode))
        self.mode_input.blockSignals(False)
        self.page_input.setRange(1, document.pageCount())
        self.page_total.setText(f" / {document.pageCount()}  ")
        self.setWindowTitle(f"{self.path.name} — B01PDF")
        self.relayout()
        self.go_to(self.page)
        self.restore_offset(state)
        self.statusBar().showMessage(str(self.path))
        return True

    def restore_offset(self, state):
        rect = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
        if rect and state:
            try:
                offset = max(-1.0, min(1.0, float(state.get("offset", 0))))
                self.viewer.verticalScrollBar().setValue(round(rect.top() + offset * rect.height()))
                self.viewer.horizontalScrollBar().setValue(int(state.get("x", 0)))
            except (ValueError, TypeError):
                pass

    def show_zoom(self, value):
        self.zoom = value
        self.zoom_input.setValue(round(value))
        self.zoom_input.setToolTip(f"현재 배율: {value:.1f}%")

    def relayout(self, preserve=False):
        if self.relayouting:
            return
        self.relayouting = True
        rect = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
        offset = ((self.viewer.verticalScrollBar().value() - rect.top()) / rect.height()
                  if preserve and rect else 0)
        self.viewer.pages.layout_pages()
        self.sidebar.pages.layout_pages()
        if preserve:
            new = next((r for p, r in self.viewer.pages.rectangles if p == self.page), None)
            if new:
                self.viewer.verticalScrollBar().setValue(round(new.top() + offset * new.height()))
        self.relayouting = False
        self.show_zoom(self.zoom)

    def set_current_page(self, page):
        self.page = page
        self.page_input.setValue(page + 1)
        self.sidebar.pages.update()
        if hasattr(self, "save_timer"):
            self.save_timer.start()

    def go_to(self, page):
        if not self.document.pageCount():
            return
        page = max(0, min(self.document.pageCount() - 1, page))
        self.set_current_page(page)
        if self.view_mode != "scroll" or self.fit != "manual":
            self.relayout()
        rect = next((r for p, r in self.viewer.pages.rectangles if p == page), None)
        if rect:
            self.viewer.verticalScrollBar().setValue(max(0, rect.top() - 20))
        thumb = self.sidebar.pages.rectangles[page][1]
        self.sidebar.ensureVisible(thumb.center().x(), thumb.center().y(), 0, thumb.height() // 2 + 12)

    def set_zoom(self, value):
        self.fit = "manual"
        self.zoom = max(10, min(400, value))
        self.relayout(preserve=True)

    def set_fit(self, mode):
        self.fit = mode
        self.relayout(preserve=True)

    def change_mode(self, index):
        self.view_mode = ["single", "two", "scroll"][index]
        self.relayout()
        self.go_to(self.page)

    def change_filter(self, index):
        self.filter_mode = ["original", "sharp", "smooth"][index]
        self.cache.clear()
        self.viewer.pages.update()

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("프로그램 설정")
        layout = QVBoxLayout(dialog)
        remember = QCheckBox("닫은 페이지 위치 기억하기")
        remember.setChecked(self.remember())
        layout.addWidget(remember)
        layout.addWidget(QLabel("같은 PDF를 다시 열면 마지막 페이지와 스크롤 위치를 복원해요."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.setValue("remember", remember.isChecked())
            if not remember.isChecked():
                self.settings.remove("positions")
            else:
                self.save_position()
            self.settings.sync()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() and u.toLocalFile().lower().endswith(".pdf")
                                             for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.open_file(url.toLocalFile())
                event.acceptProposedAction()
                break

    def closeEvent(self, event):
        self.save_position()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.sync()
        self.save_timer.stop()
        self.cache.clear()
        self.document.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("B01PDF")
    app.setStyle("Fusion")
    app.setStyleSheet("QToolBar { spacing: 4px; padding: 7px; border-bottom: 1px solid #ddd; }"
                     "QToolButton { padding: 6px; } QComboBox, QSpinBox { padding: 4px; }"
                     "QStatusBar { color: #646775; } QSplitter::handle { background: #ced0d8; }")
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(500, app.quit)
    elif len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: window.open_file(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
