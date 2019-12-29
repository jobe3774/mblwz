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

from datetime import datetime, timezone
from raspend import RaspendApplication, ThreadHandlerBase
from collections import namedtuple
from pyModbusTCP.client import ModbusClient

import json
import requests
from requests.exceptions import HTTPError

ModbusRegister = namedtuple("ModbusRegister", "Address SequenceSize")

class HeatPumpConstants():
    NAN_VALUE = 0x8000
    MBREG_BITWIDTH = 16

class HeatPumpRegisters():
    def __init__(self):
        self.OUTSIDE_TEMPERATURE = ModbusRegister(6, 1)
        self.CURRENT_ROOM_TEMPERATURE = ModbusRegister(0, 1)
        self.CURRENT_SUPPLY_FAN_SPEED = ModbusRegister(17, 1)
        self.CURRENT_EXHAUST_FAN_SPEED = ModbusRegister(19, 1)
        self.AIRING_LEVEL_DAY = ModbusRegister(1017, 1)
        self.AIRING_LEVEL_NIGHT = ModbusRegister(1018, 1)
        self.POWER_CONSUMPTION_HEATING_DAY = ModbusRegister(3021, 1)
        self.POWER_CONSUMPTION_WARMWATER_DAY = ModbusRegister(3024, 1)

    def convertSignedValue(self, val, bits):
        """ Signed values are represented as two's complement.
        """
        maxValue = 2 ** (bits) - 1

        if val > maxValue or val < 0:
            raise ValueError("Out-of-range error. val = {} must be in a range of 0 to {}.".format(val, maxValue))

        limit = 2 ** (bits - 1) - 1
        if val <= limit:
            return val
        else:
            return val - 2 ** bits

    def shiftValue(self, regVal, sequenceSize):
        if regVal is None:
            return 0
        if len(regVal) != sequenceSize:
            return 0

        val = 0
        for i in range(0, sequenceSize, 1):
            val |= regVal[i]
            if i < sequenceSize-1:
                val <<= HeatPumpConstants.MBREG_BITWIDTH

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
        self.powerConsumptionHeatingDay = HeatPumpConstants.NAN_VALUE
        self.powerConsumptionWarmWaterDay = HeatPumpConstants.NAN_VALUE

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

        regVal_outsideTemperature = self.mbClient.read_input_registers(self.registers.OUTSIDE_TEMPERATURE.Address, 
                                                                       self.registers.OUTSIDE_TEMPERATURE.SequenceSize)
        regVal_currentRoomTemperature = self.mbClient.read_input_registers(self.registers.CURRENT_ROOM_TEMPERATURE.Address, 
                                                                           self.registers.CURRENT_ROOM_TEMPERATURE.SequenceSize)
        regVal_currentExhaustFanSpeed = self.mbClient.read_input_registers(self.registers.CURRENT_EXHAUST_FAN_SPEED.Address, 
                                                                           self.registers.CURRENT_EXHAUST_FAN_SPEED.SequenceSize)
        regVal_currentSupplyFanSpeed = self.mbClient.read_input_registers(self.registers.CURRENT_SUPPLY_FAN_SPEED.Address, 
                                                                          self.registers.CURRENT_SUPPLY_FAN_SPEED.SequenceSize)
        regVal_airingLevelDay = self.mbClient.read_holding_registers(self.registers.AIRING_LEVEL_DAY.Address, 
                                                                     self.registers.AIRING_LEVEL_DAY.SequenceSize)
        regVal_airingLevelNight = self.mbClient.read_holding_registers(self.registers.AIRING_LEVEL_NIGHT.Address, 
                                                                       self.registers.AIRING_LEVEL_NIGHT.SequenceSize)
        regVal_powerConsumptionHeatingDay = self.mbClient.read_input_registers(self.registers.POWER_CONSUMPTION_HEATING_DAY.Address, 
                                                                               self.registers.POWER_CONSUMPTION_HEATING_DAY.SequenceSize)
        regVal_powerConsumptionWarmWaterDay = self.mbClient.read_input_registers(self.registers.POWER_CONSUMPTION_WARMWATER_DAY.Address, 
                                                                                 self.registers.POWER_CONSUMPTION_WARMWATER_DAY.SequenceSize)

        outsideTemperature = self.registers.shiftValue(regVal_outsideTemperature, 
                                                       self.registers.OUTSIDE_TEMPERATURE.SequenceSize)

        # outsideTemperature can be less than zero
        self.outsideTemperature = self.registers.convertSignedValue(outsideTemperature, HeatPumpConstants.MBREG_BITWIDTH) * 0.1

        self.currentRoomTemperature = self.registers.shiftValue(regVal_currentRoomTemperature, 
                                                                self.registers.CURRENT_ROOM_TEMPERATURE.SequenceSize) * 0.1
        self.currentExhaustFanSpeed = self.registers.shiftValue(regVal_currentExhaustFanSpeed, 
                                                                self.registers.CURRENT_EXHAUST_FAN_SPEED.SequenceSize)
        self.currentSupplyFanSpeed = self.registers.shiftValue(regVal_currentSupplyFanSpeed, 
                                                               self.registers.CURRENT_SUPPLY_FAN_SPEED.SequenceSize)
        self.airingLevelDay = self.registers.shiftValue(regVal_airingLevelDay, 
                                                        self.registers.AIRING_LEVEL_DAY.SequenceSize)
        self.airingLevelNight = self.registers.shiftValue(regVal_airingLevelNight, 
                                                          self.registers.AIRING_LEVEL_NIGHT.SequenceSize)

        self.powerConsumptionHeatingDay = self.registers.shiftValue(regVal_powerConsumptionHeatingDay, 
                                                          self.registers.POWER_CONSUMPTION_HEATING_DAY.SequenceSize)

        self.powerConsumptionWarmWaterDay = self.registers.shiftValue(regVal_powerConsumptionWarmWaterDay, 
                                                          self.registers.POWER_CONSUMPTION_WARMWATER_DAY.SequenceSize)

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
        thisDict["powerConsumptionHeatingDay"] = HeatPumpConstants.NAN_VALUE
        thisDict["powerConsumptionWarmWaterDay"] = HeatPumpConstants.NAN_VALUE

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
        thisDict["powerConsumptionHeatingDay"] = self.heatPump.powerConsumptionHeatingDay
        thisDict["powerConsumptionWarmWaterDay"] = self.heatPump.powerConsumptionWarmWaterDay

        return 

class PushTemperatures(ThreadHandlerBase):
    def __init__(self, sectionName, csvFileName, dbUser, dbPassword, dbEndpoint):
        self.sectionName = sectionName
        self.csvFileName = csvFileName
        self.dbUser = dbUser
        self.dbPassword = dbPassword
        self.dbEndpoint = dbEndpoint
        return

    def prepare(self):
        # create a csv file for caching temperatures in case of an error
        if not os.path.isfile(self.csvFileName):
            try:
                csvFile = open(self.csvFileName, "wt")
                header = "Timestamp, Outside, Bathroom\n"
                csvFile.write(header)
                csvFile.close()
            except IOError as e:
                logging.error("Unable to open csv file '{}'! Error: {}".format(self.csvFileName, e))
        return

    def saveTemperaturesToCSVFile(self, temperatures):
        strLine = "{},{},{}\n".format(temperatures["timestamp"], temperatures["outside"], temperatures["bathroom"])
        try:
            csvFile = open(self.csvFileName, "at")
            csvFile.write(strLine)
            csvFile.close()
        except IOError as e:
            logging.error("Unable to open csv file '{}'! Error: {}".format(self.csvFileName, e))
        return


    def invoke(self):
        if not self.sectionName in self.sharedDict:
            return

        thisDict = self.sharedDict[self.sectionName]

        temperatures = dict()
        
        temperatures["timestamp"] = datetime.now(timezone.utc).timestamp()
        temperatures["outside"] = thisDict["outsideTemperature"]
        temperatures["bathroom"] = thisDict["currentRoomTemperature"]

        try:
            data = json.dumps(temperatures)
            response = requests.post(self.dbEndpoint, data, auth=(self.dbUser, self.dbPassword))
            response.raise_for_status()
        except HTTPError as http_err:
            print("HTTP error occurred: {}".format(http_err))
            self.saveTemperaturesToCSVFile(temperatures)
        except Exception as err:
            print("Unexpected error occurred: {}".format(err))
            self.saveTemperaturesToCSVFile(temperatures)
        else:
            # Response may be ok, even if the database server is unreachable.
            if response.ok == True:
                strResponseText = response.text.lower()
                if strResponseText.find("connection error:") != -1:
                    self.saveTemperaturesToCSVFile(temperatures)
            print(response.text)

        return 

def main():
    logging.basicConfig(filename='mblwz.log', level=logging.INFO)

    logging.info("Starting at {} (PID={})".format(datetime.now(), os.getpid()))

    # Check commandline arguments.
    cmdLineParser = argparse.ArgumentParser(prog="mblwz", usage="%(prog)s [options]")
    cmdLineParser.add_argument("--port", help="The port the server should listen on", type=int, required=True)
    cmdLineParser.add_argument("--hp-ip", help="The IP or hostname of the heat pump", type=str, required=True)
    cmdLineParser.add_argument("--hp-port", help="The modbus port the heat pump has configured (default: 502)", type=int, required=False, default=502)
    cmdLineParser.add_argument("--hp-unit-id", help="The heat pumps modbus unit id (default: 1)", type=int, required=False, default=1)
    cmdLineParser.add_argument("--code", help="Code number for setting airing levels", type=int, required=False, default=0)
    cmdLineParser.add_argument("--db-user", help="User name for database log in", type=str, required=False)
    cmdLineParser.add_argument("--db-pwd", help="Password for database log in", type=str, required=False)
    cmdLineParser.add_argument("--db-endpoint", help="Endpoint used for pushing temperature data", type=str, required=False)
    cmdLineParser.add_argument("--csvFileName", help="Path to a csv file for caching temperature data in case of an error", type=str, required=False)

    try: 
        args = cmdLineParser.parse_args()
    except SystemExit:
        return

    myApp = RaspendApplication(args.port)

    mbHostName = args.hp_ip
    mbPortNumber = args.hp_port
    mbUnitId = args.hp_unit_id

    lwz404 = HeatPump(mbHostName, mbPortNumber, mbUnitId, args.code)

    myApp.addCommand(lwz404.setAiringLevelDay)
    myApp.addCommand(lwz404.setAiringLevelNight)

    myApp.createWorkerThread(HeatPumpReader("stiebel_eltron_lwz404_trend", HeatPump(mbHostName, mbPortNumber, mbUnitId, args.code)), 5)

    if len(args.db_user) and len(args.db_endpoint):
        # push temperatures every 5 minutes
        myApp.createWorkerThread(PushTemperatures("stiebel_eltron_lwz404_trend", args.csvFileName, args.db_user, args.db_pwd, args.db_endpoint), 5*60)

    myApp.run()

    logging.info("Stopped at {} (PID={})".format(datetime.now(), os.getpid()))

if __name__ == "__main__":
    main()