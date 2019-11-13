#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  mblwz - modbus lwz (reader and controller)
#
#  Reads out current values of my Stiebel Eltron LWZ 404 Trend heat pump
#  and lets me control its airing levels via HTTP.
#
#  Uses raspend for threading and command invocation.
#
#  Visit https://github.com/jobe3774/raspend to learn more about raspend.
#  
#  License: MIT
#  
#  Copyright (c) 2019 Joerg Beckers

from raspend import RaspendApplication, ThreadHandlerBase

import os

# Needed for testing on Windows
if os.name == "nt":
    import win_inet_pton

from collections import namedtuple

from pyModbusTCP.client import ModbusClient

ModbusRegister = namedtuple("ModbusRegister", "number sizeBytes")


class HeatPumpConstants():
    NAN_VALUE = 0x8000

class HeatPumpRegisters():
    def __init__(self):
        self.OUTSIDE_TEMPERATURE = ModbusRegister(6, 1)
        self.CURRENT_ROOM_TEMPERATURE = ModbusRegister(0, 1)
        self.CURRENT_EXHAUST_FAN_SPEED = ModbusRegister(17, 1)
        self.CURRENT_SUPPLY_FAN_SPEED = ModbusRegister(19, 1)
        self.AIRING_LEVEL_DAY = ModbusRegister(1017, 1)
        self.AIRING_LEVEL_NIGHT = ModbusRegister(1018, 1)

    def shiftValue(self, regVal, sizeBytes):
        if regVal is None:
            return 0
        if len(regVal) != sizeBytes:
            return 0

        val = 0
        for i in range(0, sizeBytes, 1):
            val |= regVal[i]
            if i < sizeBytes-1:
                val <<= 16

        if val == HeatPumpConstants.NAN_VALUE:
            val = 0
        return val

class HeatPump():
    def __init__(self, ipOrHostName, portNumber, unitId):
        self.registers = HeatPumpRegisters()
        self.mbClient = ModbusClient()
        self.mbClient.host(ipOrHostName)
        self.mbClient.port(portNumber)
        self.mbClient.unit_id(unitId)
        self.mbClient.open()

        self.outsideTemperature = HeatPumpConstants.NAN_VALUE
        self.currentRoomTemperature = HeatPumpConstants.NAN_VALUE
        self.currentExhaustFanSpeed = HeatPumpConstants.NAN_VALUE
        self.currentSupplyFanSpeed = HeatPumpConstants.NAN_VALUE
        self.airingLevelDay = HeatPumpConstants.NAN_VALUE
        self.airingLevelNight = HeatPumpConstants.NAN_VALUE

        return

    def setAiringLevelDay(self):
        return False

    def setAiringLevelNight(self):
        return False

    def readCurrentValues(self):
        if not self.mbClient.is_open() and not self.mbClient.open():
            print ("Unable to connect to {}:{}".format(self.mbClient.host(), self.mbClient.port()))
            return False

        regVal_outsideTemperature = self.mbClient.read_input_registers(self.registers.OUTSIDE_TEMPERATURE.number, self.registers.OUTSIDE_TEMPERATURE.sizeBytes)
        regVal_currentRoomTemperature = self.mbClient.read_input_registers(self.registers.CURRENT_ROOM_TEMPERATURE.number, self.registers.CURRENT_ROOM_TEMPERATURE.sizeBytes)
        regVal_currentExhaustFanSpeed = self.mbClient.read_input_registers(self.registers.CURRENT_EXHAUST_FAN_SPEED.number, self.registers.CURRENT_EXHAUST_FAN_SPEED.sizeBytes)
        regVal_currentSupplyFanSpeed = self.mbClient.read_input_registers(self.registers.CURRENT_SUPPLY_FAN_SPEED.number, self.registers.CURRENT_SUPPLY_FAN_SPEED.sizeBytes)
        regVal_airingLevelDay = self.mbClient.read_holding_registers(self.registers.AIRING_LEVEL_DAY.number, self.registers.AIRING_LEVEL_DAY.sizeBytes)
        regVal_airingLevelNight = self.mbClient.read_holding_registers(self.registers.AIRING_LEVEL_NIGHT.number, self.registers.AIRING_LEVEL_NIGHT.sizeBytes)

        self.outsideTemperature = self.registers.shiftValue(regVal_outsideTemperature, self.registers.OUTSIDE_TEMPERATURE.sizeBytes) * 0.1
        self.currentRoomTemperature = self.registers.shiftValue(regVal_currentRoomTemperature, self.registers.CURRENT_ROOM_TEMPERATURE.sizeBytes) * 0.1
        self.currentExhaustFanSpeed = self.registers.shiftValue(regVal_currentExhaustFanSpeed, self.registers.CURRENT_EXHAUST_FAN_SPEED.sizeBytes)
        self.currentSupplyFanSpeed = self.registers.shiftValue(regVal_currentSupplyFanSpeed, self.registers.CURRENT_SUPPLY_FAN_SPEED.sizeBytes)
        self.airingLevelDay = self.registers.shiftValue(regVal_airingLevelDay, self.registers.AIRING_LEVEL_DAY.sizeBytes)
        self.airingLevelNight = self.registers.shiftValue(regVal_airingLevelNight, self.registers.AIRING_LEVEL_NIGHT.sizeBytes)

        return True

class HeatPumpReader(ThreadHandlerBase):
    def __init__(self, heatPump):
        self.heatPump = heatPump
        return

    def prepare(self):
        self.sharedDict["outsideTemperature"] = HeatPumpConstants.NAN_VALUE
        self.sharedDict["currentRoomTemperature"] = HeatPumpConstants.NAN_VALUE
        self.sharedDict["currentExhaustFanSpeed"] = HeatPumpConstants.NAN_VALUE
        self.sharedDict["currentSupplyFanSpeed"] = HeatPumpConstants.NAN_VALUE
        self.sharedDict["airingLevelDay"] = HeatPumpConstants.NAN_VALUE
        self.sharedDict["airingLevelNight"] = HeatPumpConstants.NAN_VALUE
        return

    def invoke(self):
        if not self.heatPump.readCurrentValues():
            return

        self.sharedDict["outsideTemperature"] = self.heatPump.outsideTemperature
        self.sharedDict["currentRoomTemperature"] = self.heatPump.currentRoomTemperature
        self.sharedDict["currentExhaustFanSpeed"] = self.heatPump.currentExhaustFanSpeed
        self.sharedDict["currentSupplyFanSpeed"] = self.heatPump.currentSupplyFanSpeed
        self.sharedDict["airingLevelDay"] = self.heatPump.airingLevelDay
        self.sharedDict["airingLevelNight"] = self.heatPump.airingLevelNight

        return 

def main():
    myApp = RaspendApplication(8080)

    lwz404 = HeatPump("servicewelt", 502, 1)

    myApp.addCommand(lwz404.setAiringLevelDay)
    myApp.addCommand(lwz404.setAiringLevelNight)

    myApp.createWorkerThread(HeatPumpReader(lwz404), 5)

    myApp.run()

if __name__ == "__main__":
    main()