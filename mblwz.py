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
import os
import logging
import argparse

# Needed for testing on Windows
if os.name == "nt":
    import win_inet_pton

from datetime import datetime
from raspend import RaspendApplication, ThreadHandlerBase
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

    def convertSignedValue(self, val, sizeBytes):
        """ Signed values are represented as two's complement.
        """
        bits = sizeBytes * 8
        maxValue = 2 ** (bits) - 1

        if val > maxValue or val < 0:
            raise ValueError("Out-of-range error. val = {} must be in a range of 0 to {}.".format(val, maxValue))

        limit = 2 ** (bits - 1) - 1
        if val <= limit:
            return val
        else:
            return val - 2 ** bits

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
    def __init__(self, ipOrHostName, portNumber, unitId, code):
        self.code = code
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

    def setAiringLevelDay(self, airingLevel, code):
        return self._setAiringLevel(self.registers.AIRING_LEVEL_DAY.number, airingLevel, code)

    def setAiringLevelNight(self, airingLevel, code):
        return self._setAiringLevel(self.registers.AIRING_LEVEL_NIGHT.number, airingLevel, code)

    def _setAiringLevel(self, registerNumber, airingLevel, code):
        if int(code) != self.code:
            return (False, "Invalid security code")

        if not self.mbClient.is_open() and not self.mbClient.open():
            return (False, "Unable to connect to {}:{}".format(self.mbClient.host(), self.mbClient.port()))

        if type(airingLevel) == str:
            try:
                airingLevel = int(airingLevel)
            except:
                raise TypeError("Could not convert {} to type 'int'".format(airingLevel))

        retVal = self.mbClient.write_single_register(registerNumber, airingLevel)

        if not retVal:
            return (False, "Failed to set airing level")
        else:
            return (True, "Setting airing level successful")

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

        outsideTemperature = self.registers.shiftValue(regVal_outsideTemperature, self.registers.OUTSIDE_TEMPERATURE.sizeBytes)

        # outsideTemperature can be less than zero
        self.outsideTemperature = self.registers.convertSignedValue(outsideTemperature, 2) * 0.1

        self.currentRoomTemperature = self.registers.shiftValue(regVal_currentRoomTemperature, self.registers.CURRENT_ROOM_TEMPERATURE.sizeBytes) * 0.1
        self.currentExhaustFanSpeed = self.registers.shiftValue(regVal_currentExhaustFanSpeed, self.registers.CURRENT_EXHAUST_FAN_SPEED.sizeBytes)
        self.currentSupplyFanSpeed = self.registers.shiftValue(regVal_currentSupplyFanSpeed, self.registers.CURRENT_SUPPLY_FAN_SPEED.sizeBytes)
        self.airingLevelDay = self.registers.shiftValue(regVal_airingLevelDay, self.registers.AIRING_LEVEL_DAY.sizeBytes)
        self.airingLevelNight = self.registers.shiftValue(regVal_airingLevelNight, self.registers.AIRING_LEVEL_NIGHT.sizeBytes)

        return True

class HeatPumpReader(ThreadHandlerBase):
    def __init__(self, name, heatPump):
        self.name = name
        self.heatPump = heatPump
        return

    def prepare(self):
        if self.name not in self.sharedDict:
            self.sharedDict[self.name] = dict()
        thisDict = self.sharedDict[self.name]
        thisDict["outsideTemperature"] = HeatPumpConstants.NAN_VALUE
        thisDict["currentRoomTemperature"] = HeatPumpConstants.NAN_VALUE
        thisDict["currentExhaustFanSpeed"] = HeatPumpConstants.NAN_VALUE
        thisDict["currentSupplyFanSpeed"] = HeatPumpConstants.NAN_VALUE
        thisDict["airingLevelDay"] = HeatPumpConstants.NAN_VALUE
        thisDict["airingLevelNight"] = HeatPumpConstants.NAN_VALUE
        return

    def invoke(self):
        if not self.heatPump.readCurrentValues():
            return

        thisDict = self.sharedDict[self.name]
        thisDict["outsideTemperature"] = self.heatPump.outsideTemperature
        thisDict["currentRoomTemperature"] = self.heatPump.currentRoomTemperature
        thisDict["currentExhaustFanSpeed"] = self.heatPump.currentExhaustFanSpeed
        thisDict["currentSupplyFanSpeed"] = self.heatPump.currentSupplyFanSpeed
        thisDict["airingLevelDay"] = self.heatPump.airingLevelDay
        thisDict["airingLevelNight"] = self.heatPump.airingLevelNight

        return 

def main():
    logging.basicConfig(filename='mblwz.log', level=logging.INFO)

    logging.info("Starting at {} (PID={})".format(datetime.now(), os.getpid()))

    # Check commandline arguments.
    cmdLineParser = argparse.ArgumentParser(prog="mblwz", usage="%(prog)s [options]")
    cmdLineParser.add_argument("--port", help="The port the server should listen on", type=int, required=True)
    cmdLineParser.add_argument("--code", help="Code number for setting airing levels ", type=int, required=False, default=0)

    try: 
        args = cmdLineParser.parse_args()
    except SystemExit:
        return

    myApp = RaspendApplication(args.port)

    #hostName = "servicewelt"
    hostName = "localhost"

    lwz404 = HeatPump(hostName, 502, 1, args.code)

    myApp.addCommand(lwz404.setAiringLevelDay)
    myApp.addCommand(lwz404.setAiringLevelNight)

    myApp.createWorkerThread(HeatPumpReader("stiebel_eltron_lwz404_trend", HeatPump(hostName, 502, 1, args.code)), 5)

    myApp.run()

    logging.info("Stopped at {} (PID={})".format(datetime.now(), os.getpid()))

if __name__ == "__main__":
    main()