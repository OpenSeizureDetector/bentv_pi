#!/usr/bin/python
##########################################################################
# bentv_ui, Copyright Graham Jones 2013, 2014,2017
#    (grahamjones139@gmail.com)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
##########################################################################
# Description:
# This program is the user interface for bentv.  It does the following:
#    Monitor the Raspberry Pi GPIO input 14 (physical pin 8) to see if it
#       is pulled low by a switch connected to ground (Pin 6).
#    Each time the switch is pressed, it changes the camera view position
#       preset number, moves the camera to the camera to the new preset
#       and writes a message to the bottom of the screen.
#    The camera is moved by sending the appropriate http GET command to the
#       relevant URL on the camera.  This is done using the httplib2 library.
#    Writing to the screen is achieved using the pygame library.
#    Note that this program does NOT display the video images - this is done
#       using omxplayer, which is started separately using the bentv.sh script.
#
# User Interface:
#    The user interface uses a single button.   A short button press cycles
#       between the various modes of the user interface (camera, fit detector).
#    A long press actually does somethign, depending on the mode.  
#       In camera mode it moves the web camera around its various preset 
#          positions.
#       In fit detector mode it instructs the fit detector to save a new
#          background image.
#
# Requirements (ubuntu package names)
#    python-httplib2
#    python-pygame
#    python-netifaces
#
##########################################################################
#
import time
import sys,os
import httplib2                     # Needed to communicate with camera
import pygame                       # Needed to drive display
import socket, fcntl, struct        # Needed to get IP address
from config_utils import ConfigUtil
import json
import netifaces

haveGPIO = True
try:
    import RPi.GPIO as GPIO 
except:
    print "failed to import RPi.GPIO"
    haveGPIO = False



class bentv_ui:
    # Basic Configuration
    configFname = "config.ini"
    configSection = "bentv"
    debug = False

    # Initialise some instance variables.
    screen = None
    font = None
    textLine1 = "Camera_Mode"
    textLine2 = "Waiting for Button Press to move camera"
    presetNo = 1
    presetTxt = ['NULL','Behind Door', 'Corner', 'Chair', 'Bed']

    # UI Modes
    CAMERA_MODE = 0
    FITDECT_MODE = 1

    # Alarms
    ALARM_STATUS_OK = 0   # All ok, no alarms.
    ALARM_STATUS_WARN = 1 # Warning status
    ALARM_STATUS_FULL = 2 # Full alarm status.
    ALARM_STATUS_NOT_FOUND = 3 # Benjamin not found in image 
                               # (area below config area_threshold parameter)

    statusStrs = ("OK","Warning","ALARM!!!","Ben Not Found")
    screenBGColours = ( (0,0,255), # Blue for all ok (0)
                        (128,128,0), # Yellow for warning (1)
                        (255,0,0),  # Red for full alarm. (2)
                        (255,0,0), # Red for fall alarm. (3)
                        (128,128,0), # Yellow for fault (4)
                        (255,0,0),  # Red for manual alarm. (5)
                        (128,128,128),  # Grey for mute. (6)
                        )
    alarmStatus = 0   # Current alarm status

    # Dimensions of the status bar at the bottom of the screen.
    statusBar_x = 0
    statusBar_y = 380
    statusbar_w = 640
    statusbar_h = 100

    alarmRatioThresh = 1
    alarmRatio = 0
    specRatio = 0
    specPower = 0
    alarmPhrase = ""
    dataTime = ""


    def __init__(self):
        """Initialise the bentv_ui class - reads the configuration file
        and initialises the screen and GPIO monitor"""
        print "bentv.__init__()"
        configPath = "%s/%s" % (os.path.dirname(os.path.realpath(__file__)),
                                self.configFname)
        print configPath
        self.cfg = ConfigUtil(configPath,self.configSection)

        self.debug = self.cfg.getConfigBool("debug")
        if (self.debug): print "Debug Mode"
        
        self.debounce_ms = self.cfg.getConfigInt("debounce_ms")
        self.shortpress_ms = self.cfg.getConfigInt("shortpress_ms")
        
        self.hostname, self.ipaddr = self.getHostName()
        print self.hostname, self.ipaddr
        self.timeDown = 0.0
        self.presetNo = 1
        self.shortPress = False
        self.longPress = False
        self.initScreen()
        self.initGPIO()
        self.UIMode = self.CAMERA_MODE  # Next line changes mode to start in
                                        # FITDECT_MODE.
        self.changeUIMode()  # Initialises the messages.

    def getHostName(self):
        """Returns the hostname and IP address of the first physical 
        (non loopback) network interface as a tuple, using the 
        netifaces library..
        """
        hostname = socket.gethostname()
        ifList = netifaces.interfaces()
        print ifList
        ipAddr = "xxx.xxx.xxx.xxx"
        for ifName in ifList:
            print ifName
            if not ifName.startswith('lo'):
                print "non lo interface found ",ifName
                ifInfo = netifaces.ifaddresses(ifName).get(netifaces.AF_INET,[])
                print ifInfo
                if len(ifInfo)>0:
                    ipAddr = ifInfo[0]['addr']
                print ipAddr
        return (hostname,ipAddr)

    def initGPIO(self):
        """Initialise the GPIO pins - note we use GPIO pin numbers, not physical
        pin numbers on rpi."""
        global haveGPIO
        pinNo = self.cfg.getConfigInt("gpiono")
        self.pinNo = pinNo
        if (self.debug): print "gpioNo = %d" % pinNo
        if (haveGPIO):
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pinNo, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            # very long debounce time to prevent presses while camera is moving.
            #GPIO.add_event_detect(pinNo,
            #                      GPIO.FALLING, 
            #                      callback=self.buttonCallback
            #                      ,bouncetime=100)
        else:
            print "no GPIO - simulating camera move"
            self.moveCamera(1)

        self.lastButtonVal = 1
        self.lastButtonTime = time.time()

    def buttonCallback(self,pinNo):
        """ called on falling edge - it waits for rising edge to see how long
        the button press was. """
        print "Button Down"
        self.timeDown = time.time()
        GPIO.wait_for_edge(pinNo,GPIO.RISING)
        print "Button Up"
        print "time of press = %f" % (time.time()-self.timeDown)

    def pollButtons(self):
        """poll the buttons, and set a variable to say if we have detected
        a single, double or long click."""
        global haveGPIO
    
        if (haveGPIO):
            ip = GPIO.input(self.pinNo)
            tnow = time.time()
            if (ip != self.lastButtonVal):
                print "button state changed"
                if (ip):
                    keyPressLength = (tnow - self.lastButtonTime)*1000. #ms
                    print "Keypress Length = %f sec" % (keyPressLength)
                    if (keyPressLength<self.debounce_ms):
                        print "Ignoring very short keypress"
                        self.shortPress = False
                        self.longPress = False
                    elif (keyPressLength<self.shortpress_ms):
                        print "short press"
                        self.shortPress = True
                        self.longPress = False
                    else:
                        self.shortPress = False
                        self.longPress = True
                self.lastButtonVal = ip
                self.lastButtonTime = tnow
        else:
            pass
            # do nothing if we do not have GPIO access.

    def serviceUI(self):
        """Respond to button presses."""
        if (self.longPress):
            if (self.UIMode == self.CAMERA_MODE):
                self.moveCamera(self.pinNo)
            elif (self.UIMode == self.FITDECT_MODE):
                self.setFitDectBackground()
            else:
                print "Unrecognised UIMode %d." % self.UIMode
            self.longPress = False

        if (self.shortPress):
            self.changeUIMode()
            self.shortPress = False

    def changeUIMode(self):
        """Change the UI mode - toggle between camera and fit detector"""
        if (self.UIMode == self.CAMERA_MODE):
            print "Entering FitDetector Mode"
            self.textLine1 = "Fit Detector Mode"
            self.textLine2 = " Short press to change mode."
            self.UIMode = self.FITDECT_MODE
        else:
            print "Entering Camera Mode"
            self.textLine1 = "Camera Mode"
            self.textLine2 = " Press long button press to move camera.  Short press to change mode."
            self.UIMode = self.CAMERA_MODE
            self.alarmStatus = self.ALARM_STATUS_NOT_FOUND
        self.lastDisplayUpdateTime = time.time() #Force message to display for
                                                 # a little while before being
                                                 # overwritten.
        self.drawStatusBar()

    def drawStatusBar(self):
        """ Write the given text onto the display area of the screen"""
        try:
            # Clear screen
            self.screen.fill(self.screenBGColours[self.alarmStatus])
            # Line 1 text
            txtImg = self.font.render(self.textLine1,
                True,(255,255,255))
            self.screen.blit(txtImg,(self.statusBar_x,self.statusBar_y))
            # Line 1 time
            tnow = time.localtime(time.time())
            txtStr = "%02d:%02d:%02d " % (tnow[3],tnow[4],tnow[5])
            w = self.font.size(txtStr)[0]
            txtImg = self.font.render(txtStr,
                True,(255,255,255))
            self.screen.blit(txtImg,(self.fbSize[0]-w,self.statusBar_y))
            # Line 2 text
            txtImg = self.smallFont.render(self.textLine2,
                True,(255,255,255))
            self.screen.blit(txtImg,(self.statusBar_x,self.statusBar_y + 20))
            # Line 2 network info
            txtStr = "Host: %s, IP: %s  " % (self.hostname, self.ipaddr)
            w = self.smallFont.size(txtStr)[0]
            txtImg = self.smallFont.render(txtStr,
                                           True,
                                           (255,255,255))

            self.screen.blit(txtImg,(self.fbSize[0]-w,self.statusBar_y + 20))


            #Draw the spectrum ratio bar graph in middle of status bar.
            rx = 300
            ry=self.statusBar_y
            rw = 20
            rh = 40
            pygame.draw.rect(self.screen,(0,0,0),(rx,ry,rw,rh))
            marginPc = 100*self.specRatio/self.alarmRatioThresh
            if marginPc > 100:
                marginPc = 100
            barh = rh*marginPc/100
            if barh <2:
                barh = 2
            #print marginPc,barh
            pygame.draw.rect(self.screen,(255,0,0),(rx,ry+rh-barh,
                                                    rw,barh))

            pygame.display.update()
        except:
            print "Error in DrawStatusBar()"

    def initScreen(self):    
        """Initialise the display using the pygame library"""
        drivers = ['x11', 'fbcon', 'svgalib']
        found = False
        disp_no = os.getenv("DISPLAY")
        if disp_no:
            print "I'm running under X display = {0}".format(disp_no)
        for driver in drivers:
            # Make sure that SDL_VIDEODRIVER is set
            if not os.getenv('SDL_VIDEODRIVER'):
                os.putenv('SDL_VIDEODRIVER', driver)
            try:
                pygame.display.init()
                print 'Using Driver: {0}.'.format(driver)
            except pygame.error:
                print 'Driver: {0} failed.'.format(driver)
                continue
            found = True
            break

        if not found:
            raise Exception('No suitable video driver found!')

        self.fbSize = (pygame.display.Info().current_w, pygame.display.Info().current_h)
        print "Framebuffer size: %d x %d" % self.fbSize
        if (disp_no):
            print "Using X11 window"
            winSize = (640,480)
            self.screen = pygame.display.set_mode(winSize)
            self.fbSize = winSize
        else:
            print "Using full screen framebuffer"
            self.screen = pygame.display.set_mode(self.fbSize, pygame.FULLSCREEN)
            #print "using small screen"
            #winSize = (640,480)
            #self.screen = pygame.display.set_mode(winSize)
            #self.fbSize = winSize

        print "blank screen..."
        self.screen.fill((0, 0, 255))        
        print "initialise fonts"
        pygame.font.init()
        self.font = pygame.font.Font(None,30)
        self.smallFont = pygame.font.Font(None,16)
        print "calling drawStatusBar()"
        self.drawStatusBar()
        print "initScreen complete"

    def moveCamera(self,pinNo):
        """Callback function when button is pressed"""
        print('moveCamera called by pin number %d. PresetNo=%d' % (pinNo,self.presetNo))
        try:
            h = httplib2.Http(".cache")
            h.add_credentials(self.cfg.getConfigStr('uname'), 
                          self.cfg.getConfigStr('passwd'))
            #resp, content = h.request("http://192.168.1.24/preset.cgi?-act=goto&-status=1&-number=%d" % self.presetNo,"GET")
            resp, content = h.request("%s/%s%d" % (self.cfg.getConfigStr('camaddr'),
                                               self.cfg.getConfigStr('cammoveurl'),
                                               self.presetNo),"GET")
            print "moved to preset %d - content=%s" % (self.presetNo,content)
        except:
            print "Exception moving camera",sys.exc_info()[0]
            
        self.textLine1 = "Camera Position %d (%s)" % (self.presetNo, 
                                                       self.presetTxt[self.presetNo])
        self.presetNo += 1
        if (self.presetNo > 4): self.presetNo = 1

 

    def getOpenSeizureDetectorData(self):
        """ Use HTTP GET request to retrieve seizure detector
        data from an OpenSeizureDetector web interface.
        """
        #print "getOpenSeizureDetectorData"
        h = httplib2.Http(".cache")
        h.add_credentials(self.cfg.getConfigStr('uname'), 
                          self.cfg.getConfigStr('passwd'))
        requestStr = "%s:%s/%s" % \
                     (self.cfg.getConfigStr('benfinderserver'),
                      self.cfg.getConfigStr('benfinderport'),
                      self.cfg.getConfigStr('benfinderurl'))
        #print requestStr
        try:
            resp, content = h.request(requestStr,
                                      "GET")
            dataDict = json.loads(content)
            self.alarmStatus = int(dataDict['alarmState'])
            self.specPower = int(dataDict['specPower'])
            self.roiPower = int(dataDict['roiPower'])
            self.alarmThresh = int(dataDict['alarmThresh'])
            self.alarmRatioThresh = int(dataDict['alarmRatioThresh'])
            self.alarmPhrase = dataDict['alarmPhrase']
            self.dataTime = dataDict['dataTime']
            if (self.roiPower>self.alarmThresh):
                self.specRatio = 10*self.roiPower/self.specPower
            else:
                self.specRatio = 0
            #print "specPower=%d, roiPower=%d, specRatio=%d" % \
            #    (specPower,roiPower,specRatio)
                            
            self.textLine1 = " Ratio = %d / %d (%s)" % \
                             (self.specRatio,self.alarmRatioThresh,
                              self.alarmPhrase)
            #print dataDict['time_t']
            self.textLine2 = " Fit Detector Time = %s  " % self.dataTime
            #print resp,content
            return True
        except:
            print "getOpenSeizureDetectorData Error:",sys.exc_info()[0]
            print "getOpenSeizureDetectorData Error"
            self.textLine1 = "No Connection to Fit Detector"
            return False


        

    def run(self):
        """bentv main loop"""
        self.lastDisplayUpdateTime = time.time()
        while 1: 
            tnow = time.time()
            self.pollButtons()
            self.serviceUI()
            if (tnow-self.lastDisplayUpdateTime >= 1.0):
                if (self.UIMode == self.FITDECT_MODE):
                    self.getOpenSeizureDetectorData()
            if (tnow-self.lastDisplayUpdateTime >= 1.0):
                self.drawStatusBar()
                self.lastDisplayUpdateTime = tnow
            #print "main loop..."
            time.sleep(0.2)
        

#############################################
# Main loop - initialise the user inteface,
# then loop forever.
if __name__ == "__main__":
    bentv = bentv_ui()
    #init_screen()
    print "starting main loop..."
    bentv.run()
