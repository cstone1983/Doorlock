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


global end_Thread ## Used to end all threads on exit

relaypin = 37
red_pin = 38
green_pin = 40
white_pin = 36
blue_pin = 32
door = "Front"
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
        global end_Thread
        
        
        while (end_Thread == 0): #used to end thread if exited
            
            try:            
                reader = SimpleMFRC522() ## Setup RFID Reader
                tag_id, text = reader.read() ## Watches for Cards
                
            except:
                
                log("Error With Card Reader") ## Error with card reader
            
            else:
            
                mode = self.db.fetch('mode') ## Find Current Mode
                tag_name = self.db.fetch('tag_name') 
                ## Check for Action from UI
                
                access = self.db.check_card(tag_id, text) ## Check if card is valid in DB return true or false
                
                if (access == True): ## IF access is GRANTED
                
                    if (mode == 0): ## Door is locked - Unlock Door
                
                        self.db.update("mode", 1)
                        self.db.update("time_open", self.default_open)
                        
                    if (mode == 2): ## If Door Held Unlocked - Lock and set away in t-stat
                
                        self.db.Away()
                        
                    if (mode == 4): ## If Away mode - Unlock and remove away in t-stat
                        
                        self.db.Return()
                        
                    if (mode == 6): ## Card exists in DB - REMOVE
                    
                        if (self.db.remove(tag_id, text)):
                
                            self.db.update("mode", 0)
                
                    if (mode == 5): ## Trying to Add Card that already exists
                        
                        log("Card Already Exists")
                        
                
                elif (access == False): ## If access is DENIED
                
                    if (mode == 5): ## Card doesnt exist - ADD
                    
                        try:
                        
                            reader.write(tag_name)
                            self.db.add(tag_id, tag_name)
                        
                        except:
                        
                            log("Error Adding Card in Cards")
                        
                        else:
                        
                            self.db.update("mode", 0)
                            msg = ("Added - " + tag_name)
                            log(msg)
                    
                    if (mode == 6): ## Remove card that isnt in DB
                    
                        log("Card Not on File")
                        
                    else:    
                        log("Access Denied")
                        
                        self.db.update("mode", 3)
                        
                        time.sleep(5)
                        
                        self.db.update("mode", 0)
                     
                                    
                time.sleep(.5)
    
    
class LED(threading.Thread):
    def __init__(self, green_pin, red_pin, white_pin, blue_pin, door):
        threading.Thread.__init__(self)
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

        self.db = Database()
        
        ## Add time var to speed up responce, compare to time.now

    def run(self):
        global end_Thread
            
        # Set all LED's OFF
        self.red_off()
        self.green_off()
        self.white_off()
        self.blue_off()
        
        while (end_Thread == 0):
            self.update()
            
        
            while ((self.mode == 0) and (end_Thread == 0)):
                
                self.white_on()
                time.sleep(.5)
                self.update()
                self.white_off()
                time.sleep(.5)
                self.update()
            
            self.white_off()   
            
            while (((self.mode == 1) or (self.mode == 2)) and (end_Thread == 0)):
                
                self.green_on()
                time.sleep(.5)
                self.update()
            
            self.green_off()
            
            while ((self.mode == 3) and (end_Thread == 0)):
                self.red_on()
                time.sleep(.2)
                self.update()
                self.red_off()
                time.sleep(.2) 
                self.update()
            
            self.red_off()
                
            while ((self.mode == 4) and (end_Thread == 0)):
                self.green_on()
                time.sleep(.5)
                self.update()
                self.green_off()
                time.sleep(.5)
                self.update()
            
            self.red_off()
                
            while (((self.mode == 5) or (self.mode == 6)) and (end_Thread == 0)):
                self.blue_on()
                time.sleep(.2)
                self.blue_off()
                time.sleep(.2)
                self.update()
            self.blue_off()    
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

        global end_Thread
        now = time.time()
        
        
        while (end_Thread == 0):
            self.mode = self.db.fetch("mode")
            self.mylcd.lcd_clear()
            dsp_time = time.strftime("%-I:%M:%S %p")
            
            self.mylcd.lcd_display_string(str(dsp_time), 1)
            
            length = 3
            while ((self.mode == 0 and (end_Thread == 0))):
            
                self.mylcd.lcd_display_string("Door Locked", 2)
                self.update()
                
            self.mylcd.lcd_clear()
            while ((self.mode == 1) and (end_Thread == 0)):
                
                time_open = self.db.fetch("time_open")
                if ((len(str(time_open))) < int(length)):
                    length = len(str(time_open))
                    self.mylcd.lcd_clear()
                    
                msg = ("Unlocked - " + str(time_open) )
                
                self.mylcd.lcd_display_string(msg, 2)
                self.update()
            self.mylcd.lcd_clear()
            while ((self.mode == 2) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Held Open", 2)
                self.update()
            self.mylcd.lcd_clear()
            while ((self.mode == 3) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Access Denied", 2)
                self.update()
            self.mylcd.lcd_clear()
            while ((self.mode == 4) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Away Mode", 2)
                self.update()
            self.mylcd.lcd_clear()
            while ((self.mode == 5) and (end_Thread == 0)):
                tag_name = self.db.fetch("tag_name")
                dsp_txt = "Swipe " + str(tag_name)
                self.mylcd.lcd_display_string(dsp_txt, 2)
                self.update()
            self.mylcd.lcd_clear()
            while ((self.mode == 6) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Swipe to Remove", 2)
                self.update()
            self.mylcd.lcd_clear()    
            time.sleep(.2)    
            
        self.mylcd_clear()
        self.update()
        self.mylcd.lcd_display_string("Exiting", 2)

    def update(self):
        time.sleep(.2)
        self.mode = self.db.fetch("mode")
        dsp_time = time.strftime("%-I:%M:%S %p")
        self.mylcd.lcd_display_string(str(dsp_time), 1)
        
class Menu_System(threading.Thread):
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
        self.db = Database()
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
                name = input("Who is this tag for?")
                try:
                    self.db.update("tag_name", name)
                    self.db.update("mode", 5)
                except:
                    print("Error")
            elif (action == "Remove"):
                self.db.update("mode", 6)
            elif (action == "Open"):
                sec = input("How Long (sec)?")
                if (sec == "99"):
                    self.db.update("mode", 2)
                else:
                    self.db.update("mode", 1)
                    self.db.update("time_open", sec)
            elif (action == "Close"):
                door = Door(self.door)
                door.Door_Close()
                db.update("mode", 0)
            elif (action == "Cancel"):
                if (self.db.fetch('mode') == (5 or 6)):
                    self.db.update('mode', 0)
                    log("Canceling Action")
                    
                else:
                    log("No Action to Cancel")
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
                    end_time = self.now + int(self.db.fetch("time_open"))
                except:
                    log("Error in Mode 1 Door")
                else:
                    while ((end_time >= self.now) and (self.mode == 1)):
                        time_left = (end_time - self.now)
                        self.db.update("time_open", int(time_left))
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
            self.db.mqtt_unlocked()
    
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
            self.db.mqtt_locked()

class Database():
    def __init__(self, host="192.168.68.112", user="pi", password="python", db="doorlock", door="Front"):
       self.db_host = host
       self.db_user = user
       self.db_pass = password
       self.db = db
       self.door = door
       self.default_open = 10
       self.mqtt_connect()
       
    def connection(self):
        conn = False
        while (conn == False):
            try:
                self.conn = MySQLdb.connect(self.db_host,self.db_user,self.db_pass,self.db, port=3306 )
                self.c = self.conn.cursor (MySQLdb.cursors.DictCursor)    
            except:
                log("Error Connecting to DB in Database.connection")
            else:
                conn = True
    def close(self):
        self.conn.close()
                       
    def action(self, act):
        self.connection()
        
        def not_found():
            log("Action " + act + " Not Found")
        act_name = getattr(self, act, not_found)
        self.act_name()
        self.close()
    def fetch(self, field):
        self.connection()
        try:
            sql = ("SELECT " + str(field) + " FROM settings WHERE door = '" + str(self.door) + "'")
            self.c.execute(sql)
            row = self.c.fetchone()
            return(row[field])
        except:
            error = ("Error in SQL Fetch - " + sql)
            self.log(error)
        else:
            self.close()
    def mqtt_connect(self):
        
       self.mq = mqtt.Client()
       self.mq.connect("192.168.68.112")
       self.mq.loop_start()
    
            
    def update(self, field, value):
        self.connection()
        try:
            sql = ("UPDATE settings SET " + str(field) + " = '" + str(value) + "' WHERE door = '" + str(self.door) + "'")
            self.c.execute(sql)
            self.conn.commit()
            
        except:
            error = ("Error in SQL Update - " + sql)
            self.log(error)
        self.close()
        
    def log(self, message):
        now = datetime.now()
        string_Time = now.strftime('%b-%d-%I:%M:%S')
        log_Info = str("\n" + string_Time + " - " + str(message))
        print(log_Info)
    
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
        self.log("Adding")
        try:
            sql = ("INSERT into rfid (tag_id, tag_name) VALUES (" + str(tag_id) + ", '" + str(name) + "')")
            self.c.execute(sql)
            self.conn.commit()
        except:
            log("Error Adding Card")
        else:
            print("Added - " + str(name))
           
        self.close()
    def remove(self, tag_id, name):
        self.connection()
        log("Removing")
        try:
            
            sql = ("DELETE FROM rfid WHERE tag_id = '" + str(tag_id) + "'")
            self.c.execute(sql)
            self.conn.commit()
        except:
            log("Error Removing Tag")
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
            log(error)
    
    
    def t_stat_fetch(self, field, zone):
        try:
            conn = MySQLdb.connect("192.168.68.112","pi","python","thermostat", port=3306 )
            c = conn.cursor (MySQLdb.cursors.DictCursor)
            sql = ("SELECT " + str(field) + " FROM settings WHERE zone = '" + str(zone) + "'")
            c.execute(sql)
            row = c.fetchone()
            return(row[field])
        except:
            log("Error in t-stat fetch")
            
    def mqtt_unlocked(self):
        #self.mqtt_connect()
        self.mq.publish("/door/front/status", "unlocked")
        #self.mq.disconnect()
    def mqtt_locked(self):
        #self.mqtt_connect()
        self.mq.publish("/door/front/status", "locked")
        #self.mq.disconnect()
    def mqtt_clear(self):
        self.mq.publish("/door/front/mode", "0", retain=True)
        print("Cleared mqtt")
def Alert(body):
   
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
      urllib.parse.urlencode({
            "token": "asawaoivxp185rmcc4ie9juczr9tp6",
            "user": "u9yffbyi7ppxhcw79xwfwg5afhszk2",
            "message": body,
        }), { "Content-type": "application/x-www-form-urlencoded" })
    conn.getresponse()
    log(body)
    
def screen_print():
    now = datetime.now()
    string_Time = now.strftime('%b-%d-%I:%M:%S')
    string_Info = str("\n" + string_Time)
    
    return string_Info

    print(string_Info)
    
def log(message):
    now = datetime.now()
    string_Time = now.strftime('%b-%d-%I:%M:%S')
    log_Info = str("\n" + string_Time + " - " + str(message))
    print(log_Info)
    

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
    log("Error Starting User Input")
## Start Watching for card scans
try:

    cards = Cards(door)
    cards.start()
except:
    log("Error Starting User Input")
## Start LED Manager
try:

    led_status = LED(green_pin, red_pin, white_pin, blue_pin, door)
    led_status.start()
except:
    log("Error Starting Led Status")
## Start LCD Manager
try:

    lcd_status = lcd_status(door)
    lcd_status.start()
except:
    log("Error Starting LCD Status")
    
## Start Door Control
try:
    
    door_control = Door(door)
    door_control.start()
except:
    log("Error Starting Door Control")

def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))
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


db = Database()
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect("192.168.68.112", 1883, 60)
client.loop_start()

GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
GPIO.setup(7, GPIO.IN, pull_up_down=GPIO.PUD_UP)


while (end_Thread == 0):
    input_state = GPIO.input(7)
    
    if (input_state == False):
    
        mode = db.fetch("mode")
      
        if (mode == 0):
        
            try:
                db.update("mode", 2)
                
            except:
                log("Failed to Set Mode in Button Unlock")
                
                    
        elif(mode == 2):
                try:
                    db.update("mode", 0)
                except:
                    log("Failed to Set Mode in Button Unlock")
               

    time.sleep(.2)
    
