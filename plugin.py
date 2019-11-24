"""
AC Aircon Smart Remote plugin for Domoticz
Author: MrErwan,
Version:    0.0.1: alpha
Version:    0.1.1: beta
"""
"""
<plugin key="AC-ASRplus" name="AC Aircon Smart Remote PLUS" author="MrErwan" version="0.1.1" externallink="https://github.com/Erwanweb/ASR-Plus.git">
    <description>
        <h2>Aircon Smart Remote</h2><br/>
        Easily implement in Domoticz an full control of air conditoner controled by IR Remote and using AC Aircon Smart Remote solution<br/>
        <h3>Set-up and Configuration</h3>
    </description>
    <params>
        <param field="Address" label="Domoticz IP Address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Port" width="40px" required="true" default="8080"/>
        <param field="Username" label="Climodom IP" width="200px" required="false" default=""/>
        <param field="Password" label="Remote MAC" width="200px" required="false" default=""/>
        <param field="Mode2" label="Pause sensors" (csv list of idx)" width="100px" required="false" default=""/>
        <param field="Mode3" label="Presence Sensors (csv list of idx)" width="100px" required="false" default=""/>
        <param field="Mode4" label="Inside Temperature Sensors (csv list of idx)" width="100px" required="false" default="0"/>
        <param field="Mode5" label="Day/Night Activator, Pause On delay, Pause Off delay, Presence On delay, Presence Off delay (all in minutes), reducted T (in degree)" width="200px" required="true" default="0,1,1,2,45,3"/>
        <param field="Mode6" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal"  default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
#uniquement pour les besoins de cette appli
import getopt, sys
#pour lire le json
import json
import urllib
import urllib.parse as parse
import urllib.request as request
from datetime import datetime, timedelta
import time
import base64
import itertools



class deviceparam:

    def __init__(self,unit,nvalue,svalue):
        self.unit = unit
        self.nvalue = nvalue
        self.svalue = svalue
        self.debug = False




class BasePlugin:
    enabled = True
    powerOn = 0
    SRindex = 1
    runCounter = 0
    httpConnSensorInfo = None
    httpConnControlInfo = None
    httpConnSetControl = None

    def __init__(self):
        self.debug = False
        self.setpoint = 21.0
        self.ModeManual = True
        self.ModeAuto = False
        self.DayNight = 0
        self.DTDayNight = 0
        self.Night = False
        self.DTpresence = []
        self.Presencemode = False
        self.Presence = True
        self.PresenceTH = True
        self.presencechangedtime = datetime.now()
        self.PresenceDetected = True
        self.DTtempo = datetime.now()
        self.presenceondelay = 2  # time between first detection and last detection before turning presence ON
        self.presenceoffdelay = 45  # time between last detection before turning presence OFF
        self.pauseondelay = 1
        self.pauseoffdelay = 1
        self.pause = False
        self.pauserequested = False
        self.pauserequestchangedtime = datetime.now()
        self.reductedsp = 3
        self.InTempSensors = []
        self.intemp = 20.0
        self.nexttemps = datetime.now()
        return

    def onStart(self):
        Domoticz.Log("onStart called")
        # setup the appropriate logging level
        try:
            debuglevel = int(Parameters["Mode6"])
        except ValueError:
            debuglevel = 0
            self.loglevel = Parameters["Mode6"]
        if debuglevel != 0:
            self.debug = True
            Domoticz.Debugging(debuglevel)
            DumpConfigToLog()
            self.loglevel = "Verbose"
        else:
            self.debug = False
            Domoticz.Debugging(0)

        # create the child devices if these do not exist yet
        devicecreated = []
        if 1 not in Devices:
            Domoticz.Device(Name="Connexion", Unit=1, TypeName = "Selector Switch",Switchtype = 2, Used =1).Create()
            devicecreated.append(deviceparam(1, 0, ""))  # default is Off
        if 2 not in Devices:
            Domoticz.Device(Name = "ASR Index",Unit=2,Type = 243,Subtype = 6,).Create()
            devicecreated.append(deviceparam(2,0,"1"))  # default is Index 1
        if 3 not in Devices:
            Domoticz.Device(Name="AC On/Off", Unit=3, TypeName="Switch", Image=9, Used=1).Create()
            devicecreated.append(deviceparam(3, 0, ""))  # default is Off
        if 4 not in Devices:
            Options = {"LevelActions":"||",
                       "LevelNames":"Off|Auto|Cool|Heat|Dry|Fan",
                       "LevelOffHidden":"true",
                       "SelectorStyle":"0"}
            Domoticz.Device(Name = "AC Manual Mode",Unit=4,TypeName = "Selector Switch",Switchtype = 18,Image = 15,
                            Options = Options,Used = 1).Create()
            devicecreated.append(deviceparam(4,0,"30"))  # default is Heating mode
        if 5 not in Devices:
            Options = {"LevelActions":"||",
                       "LevelNames":"Off|Auto|Low|Mid|High",
                       "LevelOffHidden":"true",
                       "SelectorStyle":"0"}
            Domoticz.Device(Name = "AC Manual Fan Speed",Unit=5,TypeName = "Selector Switch",Switchtype = 18,Image = 15,
                            Options = Options,Used = 1).Create()
            devicecreated.append(deviceparam(5,0,"10"))  # default is Auto mode
        if 6 not in Devices:
            Domoticz.Device(Name = "AC Setpoint",Unit=6,Type = 242,Subtype = 1).Create()
            devicecreated.append(deviceparam(6,0,"20"))  # default is 20 degrees
        if 7 not in Devices:
            Options = {"LevelActions":"||",
                       "LevelNames":"Off|Manual|Auto",
                       "LevelOffHidden":"true",
                       "SelectorStyle":"0"}
            Domoticz.Device(Name = "Wind direction (swing)",Unit=7,TypeName = "Selector Switch",Switchtype = 18,Image = 15,
                            Options = Options,Used = 1).Create()
            devicecreated.append(deviceparam(7,0,"10"))  # default is Manual
        if 8 not in Devices:
            Domoticz.Device(Name="Presence sensor", Unit=8, TypeName="Switch", Image=9).Create()
            devicecreated.append(deviceparam(8, 0, ""))  # default is Off
        if 9 not in Devices:
            Options = {"LevelActions":"||",
                       "LevelNames":"Disconnected|Off|Auto|Manual",
                       "LevelOffHidden":"true",
                       "SelectorStyle":"0"}
            Domoticz.Device(Name = "Control",Unit=9,TypeName = "Selector Switch",Switchtype = 18,Image = 9,
                            Options = Options,Used = 1).Create()
            devicecreated.append(deviceparam(9,0,"10"))  # default is Off
        if 10 not in Devices:
            Domoticz.Device(Name = "Thermostat Setpoint",Unit=10,Type = 242,Subtype = 1,Used = 1).Create()
            devicecreated.append(deviceparam(10,0,"21"))  # default is 21 degrees
        if 11 not in Devices:
            Domoticz.Device(Name="Pause requested", Unit=11, TypeName="Switch", Image=9).Create()
            devicecreated.append(deviceparam(11, 0, ""))  # default is Off
        if 12 not in Devices:
            Domoticz.Device(Name="Room temp", Unit=6, TypeName="Temperature").Create()
            devicecreated.append(deviceparam(12, 0, "20"))  # default is 20 degrees

        # if any device has been created in onStart(), now is time to update its defaults
        for device in devicecreated:
            Devices[device.unit].Update(nValue = device.nvalue,sValue = device.svalue)

        # build lists of sensors and switches
        self.DTpresence = parseCSV(Parameters["Mode3"])
        Domoticz.Debug("DTpresence = {}".format(self.DTpresence))
        self.InTempSensors = parseCSV(Parameters["Mode4"])
        Domoticz.Debug("Inside Temperature sensors = {}".format(self.InTempSensors))

        # splits additional parameters
        params = parseCSV(Parameters["Mode5"])
        if len(params) == 6:
            self.DTDayNight = CheckParam("Day/Night Activator",params[1],0)
            self.pauseondelay = CheckParam("Pause On Delay",params[2],1)
            self.pauseoffdelay = CheckParam("Pause Off Delay",params[3],1)
            self.presenceondelay = CheckParam("Presence On Delay",params[4],2)
            self.presenceoffdelay = CheckParam("Presence Off Delay",params[5],45)
            self.reductedsp = CheckParam("Reduction temp",params[6],3)
        else:
            Domoticz.Error("Error reading Mode5 parameters")

        self.httpConnControlInfo = Domoticz.Connection(Name = "Control Info",Transport = "TCP/IP",Protocol = "HTTP",
                                                      Address = Parameters["Username"],Port = "80")
        self.httpConnControlInfo.Connect()

        self.httpConnSetControl = Domoticz.Connection(Name = "Set Control",Transport = "TCP/IP",Protocol = "HTTP",
                                                      Address = Parameters["Username"],Port = "80")

    def onStop(self):
        Domoticz.Log("onStop called")
        Domoticz.Debugging(0)

    def onConnect(self,Connection,Status,Description):
        Domoticz.Log("onConnect called")
        if (Status == 0):
            Domoticz.Debug("Connection successful")

            data = ''
            headers = {'Content-Type':'text/xml; charset=utf-8', \
                       'Connection':'keep-alive', \
                       'Accept':'Content-Type: text/html; charset=UTF-8', \
                       'Host':Parameters["Mode1"] + ":80", \
                       'User-Agent':'Domoticz/1.0'}

            if (Connection == self.httpConnControlInfo):
                Domoticz.Debug("Control connection created")
                requestUrl = "/api_chunghopserver?status=minify"
                Connection.Send({"Verb":"GET","URL":requestUrl,"Headers":headers})
            elif (Connection == self.httpConnSetControl):
                Domoticz.Debug("Set connection created")
                requestUrl = self.buildCommandString()
                Connection.Send({"Verb":"POST","URL":requestUrl,"Headers":headers})
        else:
            Domoticz.Debug("Connection failed")

    def onMessage(self,Connection,Data):
        Domoticz.Log("onMessage called")

        dataDecoded = Data["Data"].decode("utf-8","ignore")
        # on lit Data comme du json

        jsonStatus = json.loads(dataDecoded)

        # Domoticz.Debug("Received data from connection " + Connection.Name + ": " + jsonStatus)

        if (Connection == self.httpConnControlInfo):

            # on met id a -1 pour valider que l'on a bien trouve la telecommande

            id = -1

            # on parcourt toute la liste des telecommandes

            for remoteObject in jsonStatus["Remotes"]:

                # on regarde si c'est la bonne adresse MAC

                if Parameters["Password"] == remoteObject["MACAddress"]:
                    # on releve les valeurs

                    id = remoteObject["Index"]

                    connex = remoteObject["ActiveReception"]

                    mac = remoteObject["MACAddress"]

                    onoff = remoteObject["OnOff"]

                    mode = remoteObject["Mode"]

                    fanspeed = remoteObject["FanSpeed"]

                    stemp = remoteObject["Temperature"]

                    winmode = remoteObject["WindDirection"]


            # si la telecommande est trouvee...

            if id > -1:

                Domoticz.Debug(
                    "mac: " + mac + ";Index: " + str(id) + ";connex:" + str(connex))

                Domoticz.Debug(
                    "Power: " + onoff + "; Mode: " + mode + "; FanSpeed:" + fanspeed + "; AC Set temp: " + str(stemp)+ "; Wmode: " + winmode )

            # Server SR index
            Devices[2].Update(nValue = 0,sValue = str(id))

            # SR connexion
            if (connex == 0):
                Devices[1].Update(nValue = 0,sValue = "0")
                Devices[3].Update(nValue = 0,sValue = "0")
                Devices[4].Update(nValue = 0,sValue = "0")
                Devices[5].Update(nValue = 0,sValue = "0")
                Devices[7].Update(nValue = 0,sValue = "0")
                Devices[9].Update(nValue = 0,sValue = "0")
            else:
                Devices[1].Update(nValue = 1,sValue = "100")

                # Power
                if (onoff == "ON"):
                    self.powerOn = 1
                    sValueNew = "100"  # on
                else:
                    self.powerOn = 0
                    sValueNew = "0"  # off

                if (Devices[3].nValue != self.powerOn or Devices[2].sValue != sValueNew):
                    Devices[3].Update(nValue = self.powerOn,sValue = sValueNew)

                # Control
                if self.powerOn:
                    if self.ModeAuto:
                        Devices[9].Update(nValue = self.powerOn,sValue = "20")
                    elif self.ModeManual:
                        Devices[9].Update(nValue = self.powerOn,sValue = "30")
                else:
                    Devices[9].Update(nValue = self.powerOn,sValue = "10")

                # Mode
                if (mode == "AUTO"):
                   sValueNew = "10"  # Auto
                elif (mode == "COOL"):
                   sValueNew = "20"  # Cool
                elif (mode == "HEAT"):
                   sValueNew = "30"  # Heat
                elif (mode == "DRY"):
                   sValueNew = "40"  # Dry
                elif (mode == "FAN"):
                   sValueNew = "50"  # Fan

                if (Devices[4].nValue != self.powerOn or Devices[4].sValue != sValueNew):
                   Devices[4].Update(nValue = self.powerOn,sValue = sValueNew)

                # fanspeed
                if (fanspeed == "AUTO"):
                   sValueNew = "10"  # Auto
                elif (fanspeed == "LOW"):
                   sValueNew = "20"  # Low
                elif (fanspeed == "MID"):
                   sValueNew = "30"  # Mid
                elif (fanspeed == "HIGH"):
                   sValueNew = "40"  # High

                if (Devices[5].nValue != self.powerOn or Devices[5].sValue != sValueNew):
                    Devices[5].Update(nValue = self.powerOn,sValue = sValueNew)

                # AC Setpoint
                Devices[6].Update(nValue = stemp,sValue = str(stemp))
                if self.ModeManual:
                    Devices[10].Update(nValue = 0,sValue = (Devices[6].sValue))  # Thermostat setpoint = AC setpoint
                    self.setpoint = float(Devices[6].sValue)
                if self.ModeAuto:
                    if self.PresenceTH:
                        Devices[10].Update(nValue = 0,sValue = (Devices[6].sValue))  # Thermostat setpoint = AC setpoint
                        self.setpoint = float(Devices[6].sValue)

                # wind direction (swing)
                if (winmode == "MANUAL"):
                   sValueNew = "10"  # Manual
                elif (winmode == "AUTO"):
                   sValueNew = "20"  # Auto

                if (Devices[7].nValue != self.powerOn or Devices[7].sValue != sValueNew):
                    Devices[7].Update(nValue = self.powerOn,sValue = sValueNew)

                # full check the params if ModeAuto is ON, and update the setting if necessary
                if self.ModeAuto:
                    if Devices[4].sValue == "30" and Devices[6].nValue == self.setpoint:
                        Domoticz.Log("Setting OK in AutoMode")
                    else:
                        Devices[4].Update(nValue = self.powerOn,sValue = "30")  # Mode is Heat in Automode
                        Devices[6].Update(nValue = 0,sValue = str(self.setpoint))
                        self.httpConnSetControl.Connect()


        # Force disconnect, in case the ASR unit doesn't disconnect
        if (Connection.Connected()):
           Domoticz.Debug("Close connection")
           Connection.Disconnect()

    def onCommand(self,Unit,Command,Level,Color):
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

        if (Unit == 3):
            if (Command == "On"):
                self.powerOn = 1
                Devices[3].Update(nValue = 1,sValue = "100")
            else:
                self.powerOn = 0
                Devices[3].Update(nValue = 0,sValue = "0")

                # Update state of all other devices
            Devices[4].Update(nValue = self.powerOn,sValue = Devices[4].sValue)
            Devices[5].Update(nValue = self.powerOn,sValue = Devices[5].sValue)
            Devices[6].Update(nValue = 0,sValue = Devices[6].sValue)
            Devices[7].Update(nValue = self.powerOn,sValue = Devices[7].sValue)
            Devices[9].Update(nValue = self.powerOn,sValue = Devices[9].sValue)
            Devices[10].Update(nValue = 0,sValue = Devices[10].sValue)

        if (Unit == 4):
            Devices[4].Update(nValue = self.powerOn,sValue = str(Level))

        if (Unit == 5):
            Devices[5].Update(nValue = self.powerOn,sValue = str(Level))

        if (Unit == 7):
            Devices[7].Update(nValue = self.powerOn,sValue = str(Level))

        if (Unit == 9):
            Devices[9].Update(nValue = self.powerOn,sValue = str(Level))
            if (Devices[9].sValue == "20"):
                self.ModeAuto = True
                self.ModeManual = False
                self.powerOn = 1
                Devices[3].Update(nValue = 1,sValue = "100")
                Devices[4].Update(nValue = self.powerOn,sValue = "30")  # AC mode Heat
                Devices[5].Update(nValue = self.powerOn,sValue = "10")  # AC Fan Speed Auto
                Devices[6].Update(nValue = 0,sValue = (Devices[10].sValue))  # AC setpoint = Thermostat setpoint

            elif (Devices[9].sValue == "30"):
                self.ModeAuto = False
                self.ModeManual = True
                self.powerOn = 1
                Devices[3].Update(nValue = 1,sValue = "100")
                Devices[10].Update(nValue = 0,sValue = (Devices[6].sValue))  # Thermostat setpoint = AC setpoint

            elif (Devices[9].sValue == "10"):
                self.powerOn = 0
                self.ModeAuto = True
                self.ModeManual = False
                Devices[3].Update(nValue = 0,sValue = "0")

        if (Unit == 10):
            Devices[10].Update(nValue = 0,sValue = str(Level))
            Devices[6].Update(nValue = 0,sValue = (Devices[10].sValue))  # AC setpoint = Thermostat setpoint
            self.setpoint = float(Devices[10].sValue)

        self.httpConnSetControl.Connect()

    def onDisconnect(self,Connection):
        Domoticz.Log("onDisconnect called")
        Domoticz.Debug("Connection " + Connection.Name + " closed.")

    def onHeartbeat(self):
        Domoticz.Log("onHeartbeat called")
        # fool proof checking.... based on users feedback
        if not all(device in Devices for device in (1, 2, 3 ,4 , 5, 6, 7, 8, 9, 10,11)):
            Domoticz.Error(
                "one or more devices required by the plugin is/are missing, please check domoticz device creation settings and restart !")
            return

        self.PresenceDetection()

        # Check if the used setpoint and fan speed is ok
        if self.powerOn :
            if self.ModeAuto :
                if self.PresenceTH :
                    self.setpoint = float(Devices[10].sValue)
                    Domoticz.Log("AUTOMode - used setpoint is normal : " + str(self.setpoint))
                    Devices[6].Update(nValue = 0,sValue = str(self.setpoint))  # AC setpoint = Thermostat setpoint
                    if self.setpoint >= (self.intemp - 0.5) and Devices[5].sValue != "40" :
                        Devices[5].Update(nValue = self.powerOn,sValue = "40")  # AC Fan Speed High
                    else :
                        if Devices[5].sValue >= "20":
                            Devices[5].Update(nValue = self.powerOn,sValue = "10")  # AC Fan Speed Auto

                else :
                    self.setpoint = (float(Devices[10].sValue) - self.reductedsp)
                    Domoticz.Log("AUTOMode - used setpoint is reducted one : " + str(self.setpoint))
                    Devices[6].Update(nValue = 0,sValue = str(self.setpoint))  # AC setpoint = Thermostat setpoint reducted
                    Devices[5].Update(nValue = self.powerOn,sValue = "10")  # AC Fan Speed Auto
            else:
                self.setpoint = float(Devices[6].sValue)

        if self.nexttemps <= now:
            # call the Domoticz json API for a temperature devices update, to get the lastest temps (and avoid the
            # connection time out time after 10mins that floods domoticz logs in versions of domoticz since spring 2018)
            self.readTemps()

        self.httpConnControlInfo.Connect()



    def WriteLog(self, message, level="Normal"):

        if self.loglevel == "Verbose" and level == "Verbose":
            Domoticz.Log(message)
        elif level == "Normal":
            Domoticz.Log(message)

    def buildCommandString(self):
        Domoticz.Log("onbuildCommandString called")

        # Select good Index of the ASR from 1 to 16
        requestUrl = "/api_chunghopserver?action=changeconfig&remote="

        if (Devices[2].sValue == "1"):
           requestUrl = requestUrl + "1"
        elif (Devices[2].sValue == "2"):
           requestUrl = requestUrl + "2"
        elif (Devices[2].sValue == "3"):
           requestUrl = requestUrl + "3"
        elif (Devices[2].sValue == "4"):
           requestUrl = requestUrl + "4"
        elif (Devices[2].sValue == "5"):
           requestUrl = requestUrl + "5"
        elif (Devices[2].sValue == "6"):
           requestUrl = requestUrl + "6"
        elif (Devices[2].sValue == "7"):
           requestUrl = requestUrl + "7"
        elif (Devices[2].sValue == "8"):
           requestUrl = requestUrl + "8"
        elif (Devices[2].sValue == "9"):
           requestUrl = requestUrl + "9"
        elif (Devices[2].sValue == "10"):
           requestUrl = requestUrl + "10"
        elif (Devices[2].sValue == "11"):
           requestUrl = requestUrl + "11"
        elif (Devices[2].sValue == "12"):
           requestUrl = requestUrl + "12"
        elif (Devices[2].sValue == "13"):
           requestUrl = requestUrl + "13"
        elif (Devices[2].sValue == "14"):
           requestUrl = requestUrl + "14"
        elif (Devices[2].sValue == "15"):
           requestUrl = requestUrl + "15"
        elif (Devices[2].sValue == "16"):
           requestUrl = requestUrl + "16"

        # Set power
        requestUrl = requestUrl + "&onoff="

        if (self.powerOn):
            requestUrl = requestUrl + "ON"
        else:
            requestUrl = requestUrl + "0FF"

        # Set mode
        requestUrl = requestUrl + "&mode="

        if (Devices[4].sValue == "0"):
            requestUrl = requestUrl + "AUTO"
        elif (Devices[4].sValue == "10"):
            requestUrl = requestUrl + "AUTO"
        elif (Devices[4].sValue == "20"):
            requestUrl = requestUrl + "COOL"
        elif (Devices[4].sValue == "30"):
            requestUrl = requestUrl + "HEAT"
        elif (Devices[4].sValue == "40"):
            requestUrl = requestUrl + "DRY"
        elif (Devices[4].sValue == "50"):
            requestUrl = requestUrl + "FAN"

        # Set fanspeed
        requestUrl = requestUrl + "&fanspeed="

        if (Devices[5].sValue == "0"):
            requestUrl = requestUrl + "AUTO"
        elif (Devices[5].sValue == "10"):
            requestUrl = requestUrl + "AUTO"
        elif (Devices[5].sValue == "20"):
            requestUrl = requestUrl + "LOW"
        elif (Devices[5].sValue == "30"):
            requestUrl = requestUrl + "MID"
        elif (Devices[5].sValue == "40"):
            requestUrl = requestUrl + "HIGH"

        # Set temp
        requestUrl = requestUrl + "&temperature="

        if (Devices[6].sValue < "16"):  # Set temp Lower than range
            Domoticz.Log("Set temp is lower than authorized range !")
            requestUrl = requestUrl + "16"
        elif (Devices[6].sValue > "30"):  # Set temp Upper than range
            Domoticz.Log("Set temp is upper than authorized range !")
            requestUrl = requestUrl + "30"
        else:
            requestUrl = requestUrl + Devices[6].sValue

        # Set windDirection (swing)
        requestUrl = requestUrl + "&winddirection="

        if (Devices[7].sValue == "10"):
            requestUrl = requestUrl + "MANUAL"
        elif (Devices[7].sValue == "20"):
            requestUrl = requestUrl + "AUTO"

        return requestUrl


    def PresenceDetection(self):

        Domoticz.Log("PresenceDetection called")

        now = datetime.now()

        if Parameters["Mode3"] == "":
            Domoticz.Debug("presence detection mode = NO...")
            self.Presencemode = False
            self.Presence = False
            self.PresenceTH = True
            Devices[8].Update(nValue = 0,sValue = Devices[8].sValue)

        else:
            self.Presencemode = True
            Domoticz.Debug("presence detection mode = YES...")


            # Build list of DT switches, with their current status
            PresenceDT = {}
            devicesAPI = DomoticzAPI("type=devices&filter=light&used=true&order=Name")
            if devicesAPI:
                for device in devicesAPI["result"]:  # parse the presence/motion sensors (DT) device
                    idx = int(device["idx"])
                    if idx in self.DTpresence:  # this is one of our DT
                        if "Status" in device:
                            PresenceDT[idx] = True if device["Status"] == "On" else False
                            Domoticz.Debug("DT switch {} currently is '{}'".format(idx,device["Status"]))
                            if device["Status"] == "On":
                                self.DTtempo = datetime.now()

                        else:
                            Domoticz.Error("Device with idx={} does not seem to be a DT !".format(idx))


            # fool proof checking....
            if len(PresenceDT) == 0:
               Domoticz.Error("none of the devices in the 'dt' parameter is a dt... no action !")
               self.Presencemode = False
               self.Presence = False
               self.PresenceTH = True
               Devices[8].Update(nValue = 0,sValue = Devices[8].sValue)
               return

            if self.DTtempo + timedelta(seconds = 30) >= now:
                self.PresenceDetected = True
                Domoticz.Debug("At mini 1 DT is ON or was ON in the past 30 seconds...")
            else:
                self.PresenceDetected = False


            if self.PresenceDetected:
                if Devices[8].nValue == 1:
                    Domoticz.Debug("presence detected but already registred...")
                else:
                    Domoticz.Log("new presence detected...")
                    Devices[8].Update(nValue = 1,sValue = Devices[8].sValue)
                    self.Presence = True
                    self.presencechangedtime = datetime.now()

            else:
                if Devices[8].nValue == 0:
                    Domoticz.Debug("No presence detected DT already OFF...")
                else:
                    Domoticz.Debug("No presence detected in the past 30 seconds...")
                    Devices[8].Update(nValue = 0,sValue = Devices[8].sValue)
                    self.Presence = False
                    self.presencechangedtime = datetime.now()


            if self.Presence:
                if not self.PresenceTH:
                    if self.presencechangedtime + timedelta(minutes = self.presenceondelay) <= now:
                        Domoticz.Debug("Presence is now ACTIVE !")
                        self.PresenceTH = True

                    else:
                        Domoticz.Debug("Presence is INACTIVE but in timer ON period !")
                elif self.PresenceTH:
                        Domoticz.Debug("Presence is ACTIVE !")
            else:
                if self.PresenceTH:
                    if self.presencechangedtime + timedelta(minutes = self.presenceoffdelay) <= now:
                        Domoticz.Debug("Presence is now INACTIVE because no DT since more than X minutes !")
                        self.PresenceTH = False

                    else:
                        Domoticz.Debug("Presence is ACTIVE but in timer OFF period !")
                else:
                    Domoticz.Debug("Presence is INACTIVE !")

    def readTemps(self):

        # set update flag for next temp update
        self.nexttemps = datetime.now() + timedelta(minutes=5)

        # fetch all the devices from the API and scan for sensors
        noerror = True
        listintemps = []
        devicesAPI = DomoticzAPI("type=devices&filter=temp&used=true&order=Name")
        if devicesAPI:
            for device in devicesAPI["result"]:  # parse the devices for temperature sensors
                idx = int(device["idx"])
                if idx in self.InTempSensors:
                    if "Temp" in device:
                        Domoticz.Debug("device: {}-{} = {}".format(device["idx"], device["Name"], device["Temp"]))
                        listintemps.append(device["Temp"])
                    else:
                        Domoticz.Error("device: {}-{} is not a Temperature sensor".format(device["idx"], device["Name"]))

        # calculate the average inside temperature
        nbtemps = len(listintemps)
        if nbtemps > 0:
            self.intemp = round(sum(listintemps) / nbtemps, 1)
            Devices[12].Update(nValue=0,
                              sValue=str(self.intemp))  # update the dummy device showing the current thermostat temp
        else:
            Domoticz.Debug("No Inside Temperature found... ")
            noerror = False


        self.WriteLog("Inside Temperature = {}".format(self.intemp), "Verbose")
        return noerror



global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection,Status,Description):
    global _plugin
    _plugin.onConnect(Connection,Status,Description)

def onMessage(Connection,Data):
    global _plugin
    _plugin.onMessage(Connection,Data)

def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def buildCommandString():
    global _plugin
    _plugin.buildCommandString()


# Plugin utility functions ---------------------------------------------------

def parseCSV(strCSV):

    listvals = []
    for value in strCSV.split(","):
        try:
            val = int(value)
        except:
            pass
        else:
            listvals.append(val)
    return listvals


def DomoticzAPI(APICall):

    resultJson = None
    url = "http://{}:{}/json.htm?{}".format(Parameters["Address"], Parameters["Port"], parse.quote(APICall, safe="&="))
    Domoticz.Debug("Calling domoticz API: {}".format(url))
    try:
        req = request.Request(url)
        # if Parameters["Username"] != "":
        #     Domoticz.Debug("Add authentification for user {}".format(Parameters["Username"]))
        #     credentials = ('%s:%s' % (Parameters["Username"], Parameters["Password"]))
        #     encoded_credentials = base64.b64encode(credentials.encode('ascii'))
        #     req.add_header('Authorization', 'Basic %s' % encoded_credentials.decode("ascii"))

        response = request.urlopen(req)
        if response.status == 200:
            resultJson = json.loads(response.read().decode('utf-8'))
            if resultJson["status"] != "OK":
                Domoticz.Error("Domoticz API returned an error: status = {}".format(resultJson["status"]))
                resultJson = None
        else:
            Domoticz.Error("Domoticz API: http error = {}".format(response.status))
    except:
        Domoticz.Error("Error calling '{}'".format(url))
    return resultJson


def CheckParam(name, value, default):

    try:
        param = int(value)
    except ValueError:
        param = default
        Domoticz.Error("Parameter '{}' has an invalid value of '{}' ! defaut of '{}' is instead used.".format(name, value, default))
    return param


# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug("'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

