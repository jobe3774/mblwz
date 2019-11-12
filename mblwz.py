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

class ReadHeatPumpValues(ThreadHandlerBase):
    def __init__(self):
        pass

    def prepare(self):
        pass

    def invoke(self):
        pass

class HeatPumpAiringLevelController():
    def __init__(self, *args, **kwargs):
        return super().__init__(*args, **kwargs)

    def setAiringLevelDay(self):
        pass

    def setAiringLevelNight(self):
        pass

def main():
    myApp = RaspendApplication(8081)

    lwzAiringCtrl = HeatPumpAiringLevelController()

    myApp.addCommand(lwzAiringCtrl.setAiringLevelDay)
    myApp.addCommand(lwzAiringCtrl.setAiringLevelNight)

    myApp.createWorkerThread(ReadHeatPumpValues(), 5)

    myApp.run()

if __name__ == "__main__":
    main()