import settings

import sys
import machine
from machine import Pin, I2C, SPI
import network
import time
import struct

import mqtt_as
mqtt_as.MQTT_base.DEBUG = True



from homie.constants import FALSE, TRUE, BOOLEAN, FLOAT, STRING
from homie.device import HomieDevice
from homie.node import HomieNode
from homie.property import HomieNodeProperty

from uasyncio import get_event_loop, sleep_ms


from max9651 import MAX9651



class VoltMeter(HomieNode):

    def __init__(self, name="mcp3428", device=None):
        super().__init__(id="mcp3428", name=name, type="sensor")
        self.device = device
        self.i2c = I2C(scl=Pin(5), sda=Pin(4))
        self.display = MAX9651()
        self.channel0 = HomieNodeProperty(
            id="channel0",
            name="channel0",
            unit="V",
            settable=False,
            datatype=FLOAT,
            default=0,
        )
        self.add_property(self.channel0)
        self.channel1 = HomieNodeProperty(
            id="channel1",
            name="channel1",
            unit="V",
            settable=False,
            datatype=FLOAT,
            default=0,
        )
        self.add_property(self.channel1)
        self.channel2 = HomieNodeProperty(
            id="channel2",
            name="channel2",
            unit="V",
            settable=False,
            datatype=FLOAT,
            default=0,
        )
        self.add_property(self.channel2)
        self.channel3 = HomieNodeProperty(
            id="channel3",
            name="channel3",
            unit="V",
            settable=False,
            datatype=FLOAT,
            default=0,
        )
        self.add_property(self.channel3)
        self.voltage_properties = [self.channel0,
                                   self.channel1,
                                   self.channel2,
                                   self.channel3]
        self.uptime = HomieNodeProperty(
            id="uptime",
            name="uptime",
            settable=False,
            datatype=STRING,
            default="PT0S"
        )
        self.add_property(self.uptime)
        self.ip = HomieNodeProperty(
            id="ip",
            name="ip",
            settable=False,
            datatype=STRING,
            default="",
        )
        self.add_property(self.ip)
        self.led = Pin(0, Pin.OUT)
        self.online_led = Pin(15, Pin.OUT)
        self.online_led.off()
        self.last_online = time.time()
        self.start = time.time()
        print("start time", self.start)
        self.measured_voltages = {}
        loop = get_event_loop()
        loop.create_task(self.measure_voltages())
        loop.create_task(self.update_data())

    async def update_data(self):
        # wait until connected
        for _ in range(60):
            print("wait until connected")
            await sleep_ms(5_000)
            if self.device.mqtt.isconnected():
                break
        # loop forever
        while True:
            while self.device.mqtt.isconnected():
                print("update data")
                print(network.WLAN().status())
                self.last_online = time.time()
                print(1)
                self.online_led.on()
                print(2)
                self.led.value(0)  # illuminate onboard LED
                for index in range(4):
                    self.voltage_properties[index].data = str(self.measured_voltages[index])
                self.uptime.data = self.get_uptime()
                self.ip.data = network.WLAN().ifconfig()[0]
                self.led.value(1)  # onboard LED off
                print("final")
                await sleep_ms(15_000)
            while not self.device.mqtt.isconnected():
                print("wait for reconnect")
                if time.time() - self.last_online > 300:   # 5 minutes
                    machine.reset()
                self.online_led.off()
                self.led.value(0)  # illuminate onboard LED
                await sleep_ms(100)
                self.led.value(1)  # onboard LED off
                await sleep_ms(1000)
            machine.reset()  # if lost connection, restart

    async def measure_voltages(self):
        while True:
            for index in range(4):
                self.i2c.writeto(104, (0b1001_1000).to_bytes(1, "big"))
                await sleep_ms(250)
                data = self.i2c.readfrom(104, 3)
                raw = int.from_bytes(data[:2], "big")
                if raw >= 0b1000_0000_0000_0000:
                    raw -= 2**16
                voltage = raw * 0.000_062_5
                voltage *= 10
                print(voltage)
                self.display.show(voltage)
                await sleep_ms(250)
                self.measured_voltages[index] = voltage

    def get_uptime(self):
        diff = int(time.time() - self.start)
        out = "PT"
        # hours
        if diff // 3600:
            out += str(diff // 3600) + "H"
            diff %= 3600
        # minutes
        if diff // 60:
            out += str(diff // 60) + "M"
            diff %= 60
        # seconds
        out += str(diff) + "S"
        return out

def main():
    print("homie main")
    homie = HomieDevice(settings)
    homie.add_node(VoltMeter(device=homie))
    homie.run_forever()

if __name__ == "__main__":
    main()
