import RPi.GPIO as GPIO
import os, subprocess, time
import threading
from datetime import datetime
import sys
import http.client, urllib
import MySQLdb
from mfrc522 import SimpleMFRC522
import I2C_LCD_driver
import paho.mqtt.client as mqtt
import logging

## Config Logging

logging.basicConfig(filename='log.log', format='%(name)s - %(levelname)s - %(message)s')

## Logging Object
logger=logging.getLogger()
logger.setLevel(logging.DEBUG)



## Door to Control
door = "Front"

global end_Thread ## Used to end all threads on exit

relaypin = 37
red_pin = 38
green_pin = 40
white_pin = 36
blue_pin = 32

end_Thread=0


##Modes
##0 - Locked - Normal 
##1 - Unlocked Temp - Card Access/Menu Unlock 
##2 - Unlocked Held - Button
##3 - Denied
##4 - Away Locked
##5 - Add Card
##6 - Remove Card
##7 -

class Cards(threading.Thread):
    ## Thread actively watches for scanned cards
    def __init__(self, door):
        threading.Thread.__init__(self)

        self.door = door
        self.default_open = 10 ## Default time to open door from card read
       
        self.db = Database() # Database object for thread
        
    def run(self):
        log("info",  str(self) + " - Thread Started")
        global end_Thread
        
        
        while (end_Thread == 0): #used to end thread if exited
            
            try:            
                reader = SimpleMFRC522() ## Setup RFID Reader
                tag_id, text = reader.read() ## Watches for Cards
                
            except:
                
                log("critical", " - Error With Card Reader") ## Error with card reader
            
            else:
                log("debug", str(self) + " - Card Read " + str(tag_id) + " - " + str(text))
                mode = self.db.fetch('mode') ## Find Current Mode
                tag_name = self.db.fetch('tag_name') 
                ## Check for Action from UI
                
                access = self.db.check_card(tag_id, text) ## Check if card is valid in DB return true or false
                
                log("debug", (str(self) + " access var " + str(access)))
                
                if (access == True): ## IF access is GRANTED
                    log("debug", str(self) + "mode " + str(mode))
                    if (mode == 0): ## Door is locked - Unlock Door
                        log("debug", str(self) + " - Running Mode 0 IF, access = True")
                        self.db.update("mode", 1)
                        self.db.update("time_open", self.default_open)
                        
                    if (mode == 2): ## If Door Held Unlocked - Lock and set away in t-stat
                        log("debug", str(self) + " - Running Mode 2 IF, access = True")
                        self.db.Away()
                        
                    if (mode == 4): ## If Away mode - Unlock and remove away in t-stat
                        log("debug", str(self) + " - Running Mode 4 IF, access = True")
                        self.db.Return()
                        
                    if (mode == 6): ## Card exists in DB - REMOVE
                        log("debug", str(self) + " - Running Mode 6 IF, access = True")
                        if (self.db.remove(tag_id, text)):
                
                            self.db.update("mode", 0)
                
                    if (mode == 5): ## Trying to Add Card that already exists
                        log("debug", str(self) + " - Running Mode 5 IF, access = True")
                        log("warning",  str(self) + "Card Already Exists")
                        
                
                elif (access == False): ## If access is DENIED
                
                    if (mode == 5): ## Card doesnt exist - ADD
                        log("debug", str(self) + " - Running Mode 5 IF, access = False")
                        try:
                        
                            reader.write(tag_name) #Write name to Card
                            self.db.add(tag_id, tag_name) #Add to DB
                        
                        except:
                        
                            log("warning",  str(self) + " - Error Adding Card in Cards")
                        
                        else:
                        
                            self.db.update("mode", 0) #Return to Locked
                            log("debug",  str(self) + " - Added " + tag_name) #Log added Tag
                    
                    if (mode == 6): ## Remove card that isnt in DB
                        log("debug", str(self) + " - Running Mode 6 IF, access = False")
                        log("warning", str(self) + " - Card Not on File") #Tried to remove tag that dosent exist
                        
                    else:    
                        log("debug",  str(self) + " - Access Denied") #Card not on file, and not trying to add or remove
                        
                        self.db.update("mode", 3)
                        
                        time.sleep(5)
                        
                        self.db.update("mode", 0)
                     
                                    
                time.sleep(.5)
    
    
class LED(threading.Thread):
    def __init__(self, green_pin, red_pin, white_pin, blue_pin, door):
        threading.Thread.__init__(self)
        
        #Setup Class Vars
        self.red = red_pin
        self.green = green_pin
        self.white = white_pin
        self.blue = blue_pin
        self.door = door
        
        ## GPIO SETUP
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.green, GPIO.OUT)
        GPIO.setup(self.white, GPIO.OUT)
        GPIO.setup(self.red, GPIO.OUT)
        GPIO.setup(self.blue, GPIO.OUT)
        
        #Create DB Object
        self.db = Database()
        
        ## Add time var to speed up responce, compare to time.now
    
    def run(self):
        log("debug",  str(self) + " - Thread Started")
        global end_Thread
            
        # Set all LED's OFF
        self.red_off()
        self.green_off()
        self.white_off()
        self.blue_off()
        
        
        while (end_Thread == 0):
            
            self.update()
            log("debug",  str(self) + " - mode = " + str(self.mode))
            #Mode 0
            while ((self.mode == 0) and (end_Thread == 0)):
                
                self.white_on()
                time.sleep(.5)
                self.update()
                self.white_off()
                time.sleep(.5)
                self.update()
            
            self.white_off()   
            log("debug",  str(self) + " - mode = " + str(self.mode))
            
            #Mode 1 or 2 - 
            while (((self.mode == 1) or (self.mode == 2)) and (end_Thread == 0)):
                
                self.green_on()
                time.sleep(.5)
                self.update()
            
            self.green_off()
            log("debug",  str(self) + " - mode = " + str(self.mode))
            
            while ((self.mode == 3) and (end_Thread == 0)):
                self.red_on()
                time.sleep(.2)
                self.update()
                self.red_off()
                time.sleep(.2) 
                self.update()
            
            self.red_off()
            log("debug",  str(self) + " - mode = " + str(self.mode))
                
            while ((self.mode == 4) and (end_Thread == 0)):
                self.green_on()
                time.sleep(.5)
                self.update()
                self.green_off()
                time.sleep(.5)
                self.update()
            
            self.red_off()
            log("debug",  str(self) + " - mode = " + str(self.mode))
                
            while (((self.mode == 5) or (self.mode == 6)) and (end_Thread == 0)):
                self.blue_on()
                time.sleep(.2)
                self.blue_off()
                time.sleep(.2)
                self.update()
            self.blue_off()    
            log("debug",  str(self) + " - mode = " + str(self.mode))
            
    def update(self):
        self.now = time.time()
        self.mode = self.db.fetch("mode")
                
    def red_on(self):
        GPIO.output(self.red, GPIO.HIGH)

    def red_off(self):
        GPIO.output(self.red, GPIO.LOW)
        
    def blue_on(self):
        GPIO.output(self.blue, GPIO.HIGH)                
        
    def blue_off(self):
        GPIO.output(self.blue, GPIO.LOW)

    def green_on(self):
        GPIO.output(self.green, GPIO.HIGH)
        
    def green_off(self):
        GPIO.output(self.green, GPIO.LOW)
        
    def white_on(self):
        GPIO.output(self.white, GPIO.HIGH)
        
    def white_off(self):
        GPIO.output(self.white, GPIO.LOW)        
        
class lcd_status(threading.Thread):
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
        self.mylcd = I2C_LCD_driver.lcd()
        self.db = Database()
        
    def run(self):
        log("info",  str(self) + " - Thread Started")
        global end_Thread
        now = time.time()
        
        while (end_Thread == 0):
        
            self.mode = self.db.fetch("mode")
            self.mylcd.lcd_clear()
            
            dsp_time = time.strftime("%-I:%M:%S %p")
            
            self.mylcd.lcd_display_string(str(dsp_time), 1)
            
            length = 3
        
            
            log("debug",  str(self) + " - mode = " + str(self.mode))
            #Mode 0
            while ((self.mode == 0 and (end_Thread == 0))):
            
                self.msg("Door Locked")
                self.update()
                
            self.mylcd.lcd_clear()
            
            #Mode 1
            while ((self.mode == 1) and (end_Thread == 0)):
                
                time_open = self.db.fetch("time_open")
                if ((len(str(time_open))) < int(length)):
                    length = len(str(time_open))
                    self.mylcd.lcd_clear()
                    
                msg = ("Unlocked - " + str(time_open) )
                
                self.msg(msg)
                self.update()
                
            self.mylcd.lcd_clear()
            
            #Mode 2
            while ((self.mode == 2) and (end_Thread == 0)):
                self.msg("Held Open")
                self.update()
            
            self.mylcd.lcd_clear()
            
            #Mode 3
            while ((self.mode == 3) and (end_Thread == 0)):
                self.msg("Access Denied")   
                self.update()
            
            self.mylcd.lcd_clear()
            
            #Mode 4
            while ((self.mode == 4) and (end_Thread == 0)):
                self.msg("Away Mode")
                self.update()
            
            self.mylcd.lcd_clear()
            
            #Mode 5
            while ((self.mode == 5) and (end_Thread == 0)):
                tag_name = self.db.fetch("tag_name")
                dsp_txt = "Swipe " + str(tag_name)
                self.msg(dsp_txt)
                self.update()
            
            self.mylcd.lcd_clear()
            
            #Mode 6
            while ((self.mode == 6) and (end_Thread == 0)):
                self.msg("Swipe to Remove")
                self.update()
            self.mylcd.lcd_clear()    
            time.sleep(.2)    
            
        self.mylcd_clear()
        self.update()
        self.msg("Exiting")

    def update(self):
        time.sleep(.2)
        self.mode = self.db.fetch("mode")
        dsp_time = time.strftime("%-I:%M:%S %p")
        self.mylcd.lcd_display_string(str(dsp_time), 1)
        
    def msg(self, msg):
        try:
            self.mylcd.lcd_display_string(str(msg), 2)
        except:
            self.mylcd = I2C_LCD_driver.lcd()
class Menu_System(threading.Thread):
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
        self.db = Database()
        log("info",  str(self) + " - Thread Started")
        
    def run(self):
        global end_Thread
        
        while (end_Thread == 0):
            mode = self.db.fetch("mode")
            
            time.sleep(.5)
            print(screen_print())
            print("Current Mode - " + str(mode))
            print("Add, Remove, Open, Close, Cancel, Quit")
            action = input("What do you want to do: ")

            if (action == "Add"):
                log("debug",  str(self) + " - Add Card Action")
                name = input("Who is this tag for?")
                try:
                    self.db.update("tag_name", name)
                    self.db.update("mode", 5)
                    log("debug",  str(self) + " - Added Card")
                except:
                    print("Error")
            elif (action == "Remove"):
                log("debug",  str(self) + " - Remove Card Action")
                self.db.update("mode", 6)
            elif (action == "Open"):
                log("debug",  str(self) + " - Open Action")
                sec = input("How Long (sec)?")
                if (sec == "99"):
                    self.db.update("mode", 2)
                    log("debug",  str(self) + " - Opening Door (hold)")
                else:
                    self.db.update("mode", 1)
                    self.db.update("time_open", sec)
                    log("debug",  str(self) + " - Opening Door " + str(sec) + " seconds")
                    
            elif (action == "Close"):
                
                door = Door(self.door)
                door.Door_Close()
                db.update("mode", 0)
                log("debug",  str(self) + " - Close Action")
                
            elif (action == "Cancel"):
                if (self.db.fetch('mode') == (5 or 6)):
                    self.db.update('mode', 0)
                    log("debug", " - Canceling Action")
                    
                else:
                    log("debug", " - No Action to Cancel")
                    
            elif (action == "Quit"):
                print("Exiting")
                Alert("Door Security Exit")
                
                end_Thread = 1
            action = 0
        GPIO.cleanup()
        
        
class Door(threading.Thread):
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
        self.now = time.time()
        self.locked = 0
        self.db = Database()
        self.mq = Mqtt_pub()
        log("info",  str(self) + " - Thread Started")
    def run(self):
        global end_Thread
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(37, GPIO.OUT) ## Relay SETUP
        self.Door_Close()
            
        while (end_Thread == 0):
            self.now = time.time()
            self.mode = self.db.fetch("mode")
            
            while (self.mode == 0):
                if (self.locked == 0):
                    self.Door_Close()
                time.sleep(.2)
                self.update()

            while (self.mode == 1):
                      
                try:
                    self.now = time.time()
                    time_open = int(self.db.fetch("time_open"))
                    end_time = self.now + time_open
                    
                except:
                    log("warning", "Error in Mode 1 Door")
                else:
                    log("debug",  str(self) + " - Entering Door Open Loop ending at " + str(end_time) + " end_time " + str(end_time) + " self.now " + str(self.now) + "now " + str(time.time()) + " time open = " + str((self.db.fetch("time_open"))))
                    self.update()
                    while ((end_time >= self.now) and (self.mode == 1)):
                        time_left = (end_time - self.now)
                        time_open = time_left
                        if (self.locked == 1):
                            self.Door_Open()
                        self.update() 
                        time.sleep(.2)
 
                    self.db.update("mode", 0)
 
                self.update()   

            while (self.mode == 2):
                if (self.locked == 1):
                    self.Door_Open()
                time.sleep(.2)
                self.update()

            while (self.mode == 3):
                if (self.locked == 0):
                    self.Door_Close()
                time.sleep(.2)
                self.update()

            while (self.mode == 4):
                if (self.locked == 0):
                    self.Door_Close()
                time.sleep(.2)
                self.update()
            self.update()   
            time.sleep(.1)    
        
    def update(self):
        self.mode = self.db.fetch("mode")
        self.now = time.time()
        
    def Door_Open(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(37, GPIO.OUT) ## Relay SETUP
        try:
            GPIO.output(37, GPIO.HIGH)
            self.locked = 0
        except:
            Alert('Error Opening Door')
        else:        
            self.mq.mqtt_unlocked()
            log("debug",  str(self) + " - Door Opened")
            Alert("Door Opened for - " + str(int(self.db.fetch("time_open"))) + " sec")
    
    def Door_Close(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(37, GPIO.OUT) ## Relay SETUP
        try:
            GPIO.output(37, GPIO.LOW)
            self.locked = 1
            
        except:
            Alert('Error Locking Door')
        else:
            self.mq.mqtt_locked()
            log("debug",  str(self) + " - Door Closed")
                
class Database():
    def __init__(self, host="192.168.68.112", user="pi", password="python", db="doorlock", door="Front"):
       self.db_host = host
       self.db_user = user
       self.db_pass = password
       self.db = db
       self.door = door
       self.default_open = 10
       
    def connection(self):
        conn = False
        while (conn == False):
            try:
                self.conn = MySQLdb.connect(self.db_host,self.db_user,self.db_pass,self.db, port=3306 )
                self.c = self.conn.cursor (MySQLdb.cursors.DictCursor)    
            except:
                log("critical", "Error Connecting to DB in Database.connection")
            else:
                conn = True
    def close(self):
        try:
            self.conn.close()
        except:
            log("critical", str(self) + " - Error in close")                       
    def fetch(self, field):
        self.connection()
        
        while True:
            try:
                sql = ("SELECT " + str(field) + " FROM settings WHERE door = '" + str(self.door) + "'")
                self.c.execute(sql)
                row = self.c.fetchone()
                return(row[field])
            except:
                error = ("Error in SQL Fetch - " + sql)
                log("critical", error)
                time.sleep(1)
                self.connection()
            else:
                self.close()
                return False        
            
    def update(self, field, value):
        
        while True:
            
            self.connection()
            try:
                sql = ("UPDATE settings SET " + str(field) + " = '" + str(value) + "' WHERE door = '" + str(self.door) + "'")
                self.c.execute(sql)
                self.conn.commit()
                
            except:
                error = ("Error in SQL Update - " + sql)
                log("critical", error)
                self.connection()
            else:
                self.close()
                return False
         
    def Away(self):
        self.connection()
        self.t_stat_update("holdtemp", 58, "Living")
        self.t_stat_update("settemp", 58, "Upstairs")
        self.t_stat_update("settemp", 58, "Kitchen")
        self.t_stat_update("hold", 1, "Living")
        self.t_stat_update("hold", 1, "Control")
        ## Set Mode to Normal (0) to lock door
        self.update("mode", 4)
        self.close()
        
    def Return(self):
        self.connection()
        self.t_stat_update("hold", 0, "Living")
        self.t_stat_update("settemp", 62, "Kitchen")
        self.t_stat_update("settemp", 58, "Upstairs")
        self.t_stat_update("hold", 0, "Control")
        self.update("time_open", self.default_open)
        self.update("mode", 1)
        self.close()
        
    def check_card(self, tag_id, name):
        self.connection()
        print("\nChecking Access for ID: " + str(tag_id))
        ## Check DB for Access    
        try:
            sql = ("SELECT * FROM rfid WHERE tag_id = '" + str(tag_id) + "'" + " AND tag_name = '" + str(name) + "'")
            self.c.execute(sql)
            row = self.c.fetchone()
        except:
            log("DB Error in Access")
        else:
            if row != None:
                print("Access Granted")
                return True
            else:
                return False
        self.close
   
    def add(self, tag_id, name):
        self.connection()
        log("debug", "Adding")
        try:
            sql = ("INSERT into rfid (tag_id, tag_name) VALUES (" + str(tag_id) + ", '" + str(name) + "')")
            self.c.execute(sql)
            self.conn.commit()
        except:
            log("warning", "Error Adding Card")
        else:
            print("Added - " + str(name))
           
        self.close()
    def remove(self, tag_id, name):
        self.connection()
        log("debug", "Removing")
        try:
            
            sql = ("DELETE FROM rfid WHERE tag_id = '" + str(tag_id) + "'")
            self.c.execute(sql)
            self.conn.commit()
        except:
            log("debug", "Error Removing Tag")
            return False
        else:
            print("Removed - " + str(name))
            return True
            
        self.close()



    def t_stat_update(self, field, value, zone):
        
        ## Create SQL and Update settings table
        try:
            conn = MySQLdb.connect("192.168.68.112","pi","python","thermostat", port=3306 )
            c = conn.cursor (MySQLdb.cursors.DictCursor)
            sql = ("UPDATE settings SET " + str(field) + " = '" + str(value) + "' WHERE zone = '" + str(zone) + "'")
            c.execute(sql)
            conn.commit()
            #log(("Changed " + str(field) + " to " + str(value) + " for zone " + str(zone)))
        except:
            error = ("Error in SQL Update - " + msg)
            log("critical", error)
    
    
    def t_stat_fetch(self, field, zone):
        try:
            conn = MySQLdb.connect("192.168.68.112","pi","python","thermostat", port=3306 )
            c = conn.cursor (MySQLdb.cursors.DictCursor)
            sql = ("SELECT " + str(field) + " FROM settings WHERE zone = '" + str(zone) + "'")
            c.execute(sql)
            row = c.fetchone()
            return(row[field])
        except:
            log("critical", "Error in t-stat fetch")



class Mqtt_pub():
                
    def __init__(self):
            
       self.mq = mqtt.Client()
       self.mq.connect("192.168.68.112")
       self.mq.loop_start()
       
    def mqtt_unlocked(self):
        #self.mqtt_connect()
        self.mq.publish("/door/front/status", "unlocked", retain=True)
        #self.mq.disconnect()
    def mqtt_locked(self):
        #self.mqtt_connect()
        self.mq.publish("/door/front/status", "locked", retain=True)
        #self.mq.disconnect()
    def mqtt_clear(self):
        self.mq.publish("/door/front/mode", "0", retain=True)
        print("Cleared mqtt")
        
        
def Alert(body):
    try:
        log("debug", "Alert Sending - " + str(body))
        conn = http.client.HTTPSConnection("api.pushover.net:443")
        conn.request("POST", "/1/messages.json",
          urllib.parse.urlencode({
                "token": "asawaoivxp185rmcc4ie9juczr9tp6",
                "user": "u9yffbyi7ppxhcw79xwfwg5afhszk2",
                "message": body,
            }), { "Content-type": "application/x-www-form-urlencoded" })
        conn.getresponse()
        
    except:
        log("warning", "Error Sending Alert " + str(body)         
        
    else:
        log("debug", "Alert Sent - " + str(body))
def screen_print():
    now = datetime.now()
    string_Time = now.strftime('%b-%d-%I:%M:%S')
    string_Info = str("\n" + string_Time)
    
    return string_Info

    print(string_Info)
    
def log(lvl, message):
    global log
    now = datetime.now()
    string_Time = now.strftime('%b-%d-%I:%M:%S')
    log_Info = str(string_Time + " - " + str(message))
    if (lvl == "info"):
        logger.info(log_Info)
    if (lvl == "debug"):
        logger.info(log_Info)
    if (lvl == "warning"):
        logger.warning(log_Info)
    if (lvl == "critical"):
        logger.critical(log_Info)
    
def button_callback(channel):
    mode = sql_fetch("mode", "Front")
    locked = sql_fetch("locked", "Front")
    print("Button Pushed")
    if (mode == 1):
        if(locked == 1):
            try:
                Door_Open(99, 2)
            except:
                log("Failed to Set Mode in Button Unlock")
            else:
                sql_update("mode", 6, door, "Unlock Via Button")
                print("After Door Open")
                
                return
    elif(mode == 6):
            try:
                sql_update("mode", 1, door, "Unlock Via Button")
            except:
                log("Failed to Set Mode in Button Unlock")
            else:
                Door_Close()
    
## Start User Interface
try:

    menu = Menu_System(door)
    menu.start()
except:
    log("critical", "Error Starting User Input")
## Start Watching for card scans
try:

    cards = Cards(door)
    cards.start()
except:
    log("critical", "Error Starting User Input")
## Start LED Manager
try:

    led_status = LED(green_pin, red_pin, white_pin, blue_pin, door)
    led_status.start()
except:
    log("critical", "Error Starting Led Status")
## Start LCD Manager
try:

    lcd_status = lcd_status(door)
    lcd_status.start()
except:
    log("critical", "Error Starting LCD Status")
    
## Start Door Control
try:
    
    door_control = Door(door)
    door_control.start()
except:
    log("critical", "Error Starting Door Control")

def on_message(client, userdata, msg):

    log("debug", msg.topic+" "+str(msg.payload))
    
    if (msg.payload.decode() == "open10"):
        db.update("time_open", 10)
        db.update("mode", 1)
    
    if (msg.payload.decode() == "open30"):
        db.update("time_open", 30)
        db.update("mode", 1)
    
    if (msg.payload.decode() == "openhold"):
        db.update("mode", 2)
    
    if (msg.payload.decode() == "close"):
        db.update("mode", 0)
    
    if (msg.payload.decode() == "away"):
        on_message_away()
    
        
def on_message_away():
    mode = db.fetch("mode")
    print(mode)
    if ((mode == 0) or (mode == 1) or (mode == 2)):
        db.Away()
    if (mode == 4):
        db.Return()   
         
def on_connect(client, userdata, flags, rc):
    #print("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("/door/front/mode")
    client.subscribe("/door/front/add")
    client.subscribe("/door/front/status")    
    
    

db = Database()



client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
## Clears any retained messages on the mode channel, eliminates triggering a door open on boot and removes any retained message from clients
client.publish("/door/front/mode", "Clear", retain=True)

client.connect("192.168.68.112", 1883, 60)
client.loop_start()

GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
GPIO.setup(7, GPIO.IN, pull_up_down=GPIO.PUD_UP)


Alert("Door Lock Started")
while (end_Thread == 0):
    input_state = GPIO.input(7)
  
    if (input_state == False):
    
        mode = db.fetch("mode")
      
        if (mode == 0):
        
            try:
                db.update("mode", 2)
                
            except:
                log("warning", "Failed to Set Mode in Button Unlock - Mode 0")
                

        elif(mode == 1):
               try:
                    db.update("mode", 0)
               except:
                    log("warning", "Failed to Set Mode in Button lock - Mode 1")
                            
        elif(mode == 2):
                try:
                    db.update("mode", 0)
                except:
                    log("warning", "Failed to Set Mode in Button lock - Mode 2")
                    
        
    time.sleep(.2)
    
