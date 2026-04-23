import sys
import time
import numpy as np
import pandas as pd
import smbus
from PyQt5 import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
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
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "Voltage", units="V")
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.enableAutoRange()

        self.plot_curves = [
            self.plot_widget.plot(pen=pg.intColor(i, hues=NCHANNELS))
            for i in range(NCHANNELS)
        ]

        layout.addWidget(self.plot_widget)

        # Channel selector
        self.channel_selector = QtWidgets.QComboBox()
        self.channel_selector.addItem("All")
        for i in range(NCHANNELS):
            self.channel_selector.addItem(f"Channel {i}")
        layout.addWidget(self.channel_selector)

        self.start_stop_button = QtWidgets.QPushButton("Start")
        layout.addWidget(self.start_stop_button)

        self.center()

    @QtCore.pyqtSlot(pd.DataFrame)
    def update_plot(self, data):
        self.plot_data = pd.concat([self.plot_data, data], ignore_index=True)

        if len(self.plot_data) > MAX_POINTS:
            self.plot_data = self.plot_data.iloc[-MAX_POINTS:]

        selected = self.channel_selector.currentText()

        if selected == "All":
            for ch in range(NCHANNELS):
                self.plot_curves[ch].setVisible(True)
                self.plot_curves[ch].setData(
                    self.plot_data["t"],
                    self.plot_data[f"Channel {ch}"]
                )
        else:
            ch = int(selected.split()[-1])
            for i in range(NCHANNELS):
                self.plot_curves[i].setVisible(i == ch)

            self.plot_curves[ch].setData(
                self.plot_data["t"],
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