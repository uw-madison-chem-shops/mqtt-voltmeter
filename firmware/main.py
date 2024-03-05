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
        self.online_led = Pin(15, Pin.OUT)
        self.online_led.off()
        self.last_online = time.time()
        self.start = time.time()
        print("start time", self.start)
        self.currently_displayed_channel = 0
        self.measured_voltages = {}
        loop = get_event_loop()
        loop.create_task(self.measure_voltages())
        loop.create_task(self.update_data())
        # interrupt on button press
        pir = Pin(2, Pin.IN)
        pir.irq(trigger=Pin.IRQ_RISING, handler=self.on_button_press)

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
                for index in range(4):
                    self.voltage_properties[index].data = str(self.measured_voltages[index])
                self.uptime.data = self.get_uptime()
                self.ip.data = network.WLAN().ifconfig()[0]
                print("final")
                await sleep_ms(15_000)
            while not self.device.mqtt.isconnected():
                print("wait for reconnect")
                if time.time() - self.last_online > 300:   # 5 minutes
                    machine.reset()
                self.online_led.off()
                await sleep_ms(1000)
            machine.reset()  # if lost connection, restart

    async def measure_voltages(self):
        while True:
            for index in range(4):
                command = 0
                command += 1 << 7  # ready bit
                command += index << 5  # channel
                command += 1 << 4  # mode
                command += 0b10 << 2  # rate
                command += 0  # gain
                self.i2c.writeto(104, command.to_bytes(1, "big"))
                await sleep_ms(250)
                data = self.i2c.readfrom(104, 3)
                raw = int.from_bytes(data[:2], "big")
                if raw >= 0b1000_0000_0000_0000:
                    raw -= 2**16
                voltage = raw * 0.000_062_5
                voltage *= 10
                print(voltage)
                self.measured_voltages[index] = voltage
                await sleep_ms(0)
            # update display
            self.display.show(self.measured_voltages[self.currently_displayed_channel])
            self.display.show_channel(self.currently_displayed_channel + 1)
            await sleep_ms(50)

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

    async def advance_channel_debounce(self):
        print("on button press")
        irq_state = machine.disable_irq()
        self.currently_displayed_channel += 1
        if self.currently_displayed_channel >= 4:
            self.currently_displayed_channel = 0
        await sleep_ms(100)
        machine.enable_irq(irq_state)

    def on_button_press(self, *args, **kwargs):
        loop = get_event_loop()
        loop.create_task(self.advance_channel_debounce())

def main():
    print("homie main")
    homie = HomieDevice(settings)
    homie.add_node(VoltMeter(device=homie))
    homie.run_forever()

if __name__ == "__main__":
    main()
