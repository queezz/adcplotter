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
        self.running = False
        self.start_stop_button.clicked.connect(self.start_stop_acquisition)

    def center(self):
        qr = self.frameGeometry()
        cp = QtWidgets.QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def setup_ui(self):
        area = DockArea()
        self.setCentralWidget(area)

        plot_dock = Dock("Plot", size=(1000, 500))
        channels_dock = Dock("Channels", size=(1000, 250))
        controls_dock = Dock("Controls", size=(1000, 60))

        area.addDock(plot_dock, "top")
        area.addDock(channels_dock, "bottom", plot_dock)
        area.addDock(controls_dock, "bottom", channels_dock)

        self.plot_widget = pg.PlotWidget()
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

        panel_widget = QtWidgets.QWidget()
        panel_layout = QtWidgets.QGridLayout(panel_widget)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setHorizontalSpacing(24)
        panel_layout.setVerticalSpacing(6)

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
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            row_layout.addWidget(cb)
            row_layout.addWidget(label)
            row_layout.addStretch()

            panel_layout.addWidget(row_widget, row, col)

            self.channel_checkboxes.append(cb)
            self.channel_labels.append(label)

        panel_layout.setRowStretch(rows, 1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(panel_widget)

        channels_dock.addWidget(scroll)

        controls_widget = QtWidgets.QWidget()
        controls_layout = QtWidgets.QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(8, 8, 8, 8)

        self.start_stop_button = QtWidgets.QPushButton("Start")
        controls_layout.addWidget(self.start_stop_button)
        controls_layout.addStretch()

        controls_dock.addWidget(controls_widget)    


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
    mainWindow.show()
    sys.exit(app.exec_())