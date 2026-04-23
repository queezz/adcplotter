import sys
import time
import numpy as np
import pandas as pd
import smbus
from PyQt5 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea, Dock
from AIO import AIO_32_0RA_IRC

NCHANNELS = 32
MAX_POINTS = 1000


class ADCWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    data_ready = QtCore.pyqtSignal(pd.DataFrame)

    def __init__(self, app, now, parent=None):
        super(ADCWorker, self).__init__(parent)
        self.adc = AIO_32_0RA_IRC(0x49, 0x3E)
        self.data_rate = self.adc.DataRate.DR_860SPS
        self.running = False
        self.app = app
        self.start_time = now

    @QtCore.pyqtSlot()
    def start(self):
        self.running = True
        self.app.processEvents()
        self.run()

    @QtCore.pyqtSlot()
    def stop(self):
        self.running = False
        self.app.processEvents()

    def read_adc(self):
        data = {}
        now = pd.Timestamp.now()
        data["Timestamp"] = now
        data["t"] = pd.Timedelta(now - self.start_time).total_seconds()

        for channel in range(NCHANNELS):
            data[f"Channel {channel}"] = self.adc.analog_read_volt(channel, self.data_rate)

        df = pd.DataFrame(data, index=[0])
        self.data_ready.emit(df)
        self.app.processEvents()

    def run(self):
        while self.running:
            self.read_adc()
            time.sleep(0.2)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.app = app
        self.setWindowTitle("ADC Data Acquisition")
        self.setup_ui()
        self.showMaximized()
        self.running = False
        self.start_stop_button.clicked.connect(self.start_stop_acquisition)

    def setup_ui(self):
        area = DockArea()
        self.setCentralWidget(area)

        # --- Docks ---
        channels_dock = Dock("Channels", size=(300, 800))
        plot_dock = Dock("Plot", size=(900, 800))
        channels_dock.setMaximumWidth(350)

        area.addDock(channels_dock, "left")
        area.addDock(plot_dock, "right", channels_dock)

        # --- Plot ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setMinimumSize(600, 400)
        self.plot_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        self.plot_widget.setLabel("left", "Voltage", units="V")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.enableAutoRange()

        self.plot_curves = [
            self.plot_widget.plot(pen=pg.intColor(i, hues=NCHANNELS))
            for i in range(NCHANNELS)
        ]

        for i in range(NCHANNELS):
            self.plot_curves[i].setVisible(i == 0)

        plot_dock.addWidget(self.plot_widget)

        # --- Channel panel ---
        panel_widget = QtWidgets.QWidget()
        panel_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Maximum
        )
        panel_layout = QtWidgets.QGridLayout(panel_widget)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setHorizontalSpacing(8)
        panel_layout.setVerticalSpacing(2)
        panel_layout.setAlignment(QtCore.Qt.AlignTop)

        self.channel_checkboxes = []
        self.channel_labels = []

        cols = 4
        rows = (NCHANNELS + cols - 1) // cols

        for i in range(NCHANNELS):
            row = i % rows
            col = i // rows

            cb = QtWidgets.QCheckBox()
            cb.setChecked(i == 0)
            cb.stateChanged.connect(self.update_visibility)

            color = pg.intColor(i, hues=NCHANNELS)
            label = QtWidgets.QLabel(f"CH{i}")
            label.setStyleSheet(f"color: {color.name()}; font-weight: bold;")

            row_widget = QtWidgets.QWidget()
            row_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Preferred,
                QtWidgets.QSizePolicy.Fixed
            )
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            row_layout.addWidget(cb)
            row_layout.addWidget(label)
            row_layout.addStretch()

            panel_layout.addWidget(row_widget, row, col)

            self.channel_checkboxes.append(cb)
            self.channel_labels.append(label)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Expanding
        )
        scroll.setWidget(panel_widget)

        # --- Channels dock container (panel + controls) ---
        channels_container = QtWidgets.QWidget()
        channels_container.setMaximumWidth(350)
        channels_container.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Expanding
        )
        channels_layout = QtWidgets.QVBoxLayout(channels_container)
        channels_layout.setContentsMargins(6, 6, 6, 6)
        channels_layout.setSpacing(6)
        channels_layout.addWidget(scroll, 1)

        self.start_stop_button = QtWidgets.QPushButton("Start")
        self.start_stop_button.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Fixed
        )
        channels_layout.addWidget(self.start_stop_button)

        channels_dock.addWidget(channels_container)

        # --- Make plot dominant ---
        plot_dock.setStretch(10, 10)
        channels_dock.setStretch(1, 1)

    def update_visibility(self):
        for i in range(NCHANNELS):
            visible = self.channel_checkboxes[i].isChecked()
            self.plot_curves[i].setVisible(visible)

        self.plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis)

    @QtCore.pyqtSlot(pd.DataFrame)
    def update_plot(self, data):
        self.plot_data = pd.concat([self.plot_data, data], ignore_index=True)

        if len(self.plot_data) > MAX_POINTS:
            self.plot_data = self.plot_data.iloc[-MAX_POINTS:]

        t = self.plot_data["t"]

        for ch in range(NCHANNELS):
            if self.channel_checkboxes[ch].isChecked():
                self.plot_curves[ch].setData(
                    t,
                    self.plot_data[f"Channel {ch}"]
                )

    def del_thread(self):
        self.adc_thread.quit()
        self.adc_thread.wait()

    def connect_worker_signals(self):
        self.adc_worker.data_ready.connect(self.update_plot)

    def reset_data(self):
        self.plot_data = pd.DataFrame()

    def start_new_thread(self):
        now = pd.Timestamp.now()
        self.adc_worker = ADCWorker(self.app, now)
        self.connect_worker_signals()
        self.reset_data()

        self.adc_thread = QtCore.QThread(self)
        self.adc_worker.moveToThread(self.adc_thread)
        self.adc_thread.started.connect(self.adc_worker.start)
        self.adc_thread.start()

    def start_stop_acquisition(self):
        if not self.running:
            self.start_new_thread()
            self.start_stop_button.setText("Stop")
            self.running = True
            return

        if self.running:
            self.running = False
            self.adc_worker.stop()
            self.del_thread()
            self.start_stop_button.setText("Start")
            return


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    mainWindow = MainWindow()
    sys.exit(app.exec_())