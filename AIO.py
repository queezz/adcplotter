"""
Source:
https://www.y2c.co.jp/i2c-r/aio-32-0ra-irc/raspberrypi-python/
"""
try:
    import smbus
except ModuleNotFoundError:
    pass
    import controlunit.smbusplug as smbus

    # if on Windows, and smbus is not installed


class PCA9554:
    class Register:
        InputPort = 0
        OutputPort = 1
        PolarityInversion = 2
        Configuration = 3

    i2c = smbus.SMBus(1)

    def __init__(self, address):
        self.address = address

    def set_direction(self, value):
        self.i2c.write_byte_data(self.address, self.Register.Configuration, value)

    def write(self, value):
        self.i2c.write_byte_data(self.address, self.Register.OutputPort, value)


class ADS1115:
    class Register:
        Conversion = 0
        Config = 1
        LoThresh = 2
        HiThresh = 3

    class SingleShotCoversion:
        NoEffect = 0
        Begin = 1

    class Mux:
        Ain0_Ain1 = 0
        Ain0_Ain3 = 1
        Ain1_Ain3 = 2
        Ain2_Ain3 = 3
        Ain0_Gnd = 4
        Ain1_Gnd = 5
        Ain2_Gnd = 6
        Ain3_Gnd = 7

    class PGA:
        PGA_6_144V = 0
        PGA_4_096V = 1
        PGA_2_048V = 2
        PGA_1_024V = 3
        PGA_0_512V = 4
        PGA_0_256V = 5

    class Mode:
        Continuous = 0
        PowerDownSingleShot = 1

    class DataRate:
        DR_8SPS = 0
        DR_16SPS = 1
        DR_32SPS = 2
        DR_64SPS = 3
        DR_128SPS = 4  # Default
        DR_250SPS = 5
        DR_475SPS = 6
        DR_860SPS = 7

    class ComparatorQueue:
        Disable = 0x03

    i2c = smbus.SMBus(1)

    def __init__(self, address):
        self.address = address

    def analog_read(self, mux, data_rate, pga):
        self.i2c.write_word_data(
            self.address,
            self.Register.Config,
            data_rate << 13
            | self.ComparatorQueue.Disable << 8
            | self.SingleShotCoversion.Begin << 7
            | mux << 4
            | pga << 1
            | self.Mode.PowerDownSingleShot,
        )

        data = 0
        while data & 0x80 == 0:
            data = self.i2c.read_byte_data(self.address, 1)

        self.i2c.write_byte_data(self.address, self.Register.Conversion, 1)

        word_data = self.i2c.read_word_data(self.address, self.Register.Conversion)
        data = (word_data << 8) & 0xFF00 | (word_data >> 8) & 0xFF
        if data >= 0x8000:
            data -= 0x10000
        return data


class AIO_32_0RA_IRC:
    class PGA:
        PGA_10_0352V = ADS1115.PGA.PGA_2_048V
        PGA_5_0176V = ADS1115.PGA.PGA_1_024V
        PGA_2_5088V = ADS1115.PGA.PGA_0_512V
        PGA_1_2544V = ADS1115.PGA.PGA_0_256V

    class DataRate:
        DR_8SPS = ADS1115.DataRate.DR_8SPS
        DR_16SPS = ADS1115.DataRate.DR_16SPS
        DR_32SPS = ADS1115.DataRate.DR_32SPS
        DR_64SPS = ADS1115.DataRate.DR_64SPS
        DR_128SPS = ADS1115.DataRate.DR_128SPS
        DR_250SPS = ADS1115.DataRate.DR_250SPS
        DR_475SPS = ADS1115.DataRate.DR_475SPS
        DR_860SPS = ADS1115.DataRate.DR_860SPS

    multiplexerSettings = 0xFF

    def __init__(self, ads1115_address, pca9554_address):
        self.ads1115 = ADS1115(ads1115_address)
        self.multiplexer = PCA9554(pca9554_address)
        self.multiplexerSettings = 0xFF
        self.multiplexer.write(self.multiplexerSettings)
        self.multiplexer.set_direction(0)

    def analog_read(self, channel, data_rate, pga):
        if channel < 16:
            extMux = (self.multiplexerSettings & 0xF0) | channel
            adcMux = ADS1115.Mux.Ain0_Gnd
        elif channel < 32:
            extMux = (self.multiplexerSettings & 0x0F) | (channel & 0x0F) << 4
            adcMux = ADS1115.Mux.Ain1_Gnd
        elif channel < 48:
            extMux = (self.multiplexerSettings & 0xF0) | channel
            adcMux = ADS1115.Mux.Ain0_Ain3
        elif channel < 64:
            extMux = (self.multiplexerSettings & 0x0F) | (channel & 0x0F) << 4
            adcMux = ADS1115.Mux.Ain1_Ain3
        elif channel < 256:
            return 0
        else:
            extMux = channel & 0xFF
            adcMux = ADS1115.Mux.Ain0_Ain1

        if self.multiplexerSettings != extMux:
            self.multiplexer.write(extMux)
            self.multiplexerSettings = extMux

        return self.ads1115.analog_read(adcMux, data_rate, pga)

    def analog_read_volt(self, channel, data_rate=DataRate.DR_128SPS, pga=PGA.PGA_10_0352V):
        if pga == self.PGA.PGA_1_2544V:
            return float(0.256 * 49 / 10 / 32767 * self.analog_read(channel, data_rate, pga))
        elif pga == self.PGA.PGA_2_5088V:
            return float(0.512 * 49 / 10 / 32767 * self.analog_read(channel, data_rate, pga))
        elif pga == self.PGA.PGA_5_0176V:
            return float(1.024 * 49 / 10 / 32767 * self.analog_read(channel, data_rate, pga))
        else:
            return float(2.048 * 49 / 10 / 32767 * self.analog_read(channel, data_rate, pga))


def main():
    aio = AIO_32_0RA_IRC(0x49, 0x3E)

    # アナログ入力値の読み出し（電圧値）（860SPS）

    for channel in range(32):
        print("CH{:d}: {:2.3f}V".format(channel, aio.analog_read_volt(channel, aio.DataRate.DR_860SPS)))


if __name__ == "__main__":
    main()
