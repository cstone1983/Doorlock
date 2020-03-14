import RPi.GPIO as GPIO
import os, subprocess, time
import threading
from datetime import datetime
import sys
import http.client, urllib
import MySQLdb
from mfrc522 import SimpleMFRC522
from gpiozero import LED
import I2C_LCD_driver


global end_Thread

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
    def run(self):
        global end_Thread
        
        while (end_Thread == 0):
            try:            
                reader = SimpleMFRC522() ## Setup RFID Reader
                tag_id, text = reader.read() ## Watches for Cards
            except:
                log("Error With Card Reader")
            else:
                mode = sql_fetch('mode', self.door) ## Find Current Mode
                tag_name = sql_fetch('tag_name', self.door)
                ## Check for Action from UI
                print (mode)
                access = self.check_card(tag_id, text)
                if (access == True):
                    if (mode == 0):
                        Door_Open(10, 1)
                        
                    if (mode == 2): ## If Door Held Unlocked - Lock and set away
                        sql_update_t_stat("holdtemp", 58, "Living", "Setting Home AWAY")
                        sql_update_t_stat("settemp", 58, "Upstairs", "Setting Home AWAY")
                        sql_update_t_stat("settemp", 58, "Kitchen", "Setting Home AWAY")
                        sql_update_t_stat("hold", 1, "Living", "Setting Home AWAY")
                        sql_update_t_stat("hold", 1, "Control", "Setting Home AWAY")
                        ## Set Mode to Normal (1)
                        sql_update("mode", 4, self.door, "Scan to set away")
                        # Lock Door
                        Door_Close()
                        
                    if (mode == 4): ##If Locked AWAY - return 
                        sql_update_t_stat("hold", 0, "Living", "Setting Home AWAY")
                        sql_update_t_stat("settemp", 62, "Kitchen", "Setting Home AWAY")
                        sql_update_t_stat("settemp", 58, "Upstairs", "Setting Home AWAY")
                        sql_update_t_stat("hold", 0, "Control", "Setting Home AWAY")
                        sql_update("mode", 0, self.door, "Return from away")
                        Door_Open(10, 1)
                        
                    if (mode == 6):
                        self.remove(tag_id, tag_name)
                elif ((access == False) and (mode ==5)):
                    reader.write(tag_name)
                    self.add(tag_id, tag_name)
                    sql_update("mode", 0, self.door, "Done Add")
                    msg = ("Added - " + tag_name)
                    log(msg)
                
                
                else:
                    log("Access Denied")
                    sql_update("mode", 3, door, "Access Denied")
                    time.sleep(5)
                    sql_update("mode", 0, door, "Access Denied")
                 
                                    
                time.sleep(.5)
    def check_card(self, tag_id, name):
        print("Checking Access for ID: " + str(tag_id))
        ## Check DB for Access    
        try:
            conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
            c = conn.cursor (MySQLdb.cursors.DictCursor)
            sql = ("SELECT * FROM rfid WHERE tag_id = '" + str(tag_id) + "'" + " AND tag_name = '" + str(name) + "'")
            c.execute(sql)
            row = c.fetchone()
        except:
            log("DB Error in Access")
        else:
            if row != None:
                print("Access Granted")
                return True
            else:
                return False
    def add(self, tag_id, name):    
        log("Adding")
        try:
            conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
            c = conn.cursor (MySQLdb.cursors.DictCursor)
            sql = ("INSERT into rfid (tag_id, tag_name) VALUES (" + str(tag_id) + ", '" + str(name) + "')")
            c.execute(sql)
            conn.commit()
        except:
            log("Error Adding Card")
        else:
            print("Added - " + str(name))
            sql_update("mode", 0, "Front", "Add Tag")
    
    def remove(self, tag_id, name):
        log("Removing")
        try:
            conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
            c = conn.cursor (MySQLdb.cursors.DictCursor)
            sql = ("DELETE FROM rfid WHERE tag_id = '" + str(tag_id) + "'")
            c.execute(sql)
            conn.commit()
        except:
            log("Error Removing Tag")
        else:
            print("Removed - " + str(name))
            sql_update("mode", 0, "Front", "Remove Tag")
    
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

        ## Add time var to speed up responce, compare to time.now

    def run(self):
        global end_Thread

        self.red_off()
        self.green_off()
        self.white_off()
        self.blue_off()
       
        while (end_Thread == 0):
            now = time.time()
            
            self.mode = sql_fetch("mode",self.door)
            
        
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
        self.mode = sql_fetch("mode", self.door)
                
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
    def run(self):

        global end_Thread
        now = time.time()
        
        
        while (end_Thread == 0):
            self.mode = sql_fetch("mode", self.door)
            self.mylcd.lcd_clear()
            dsp_time = time.strftime("%-I:%M:%S %p")
            
            self.mylcd.lcd_display_string(str(dsp_time), 1)
            
            
            while ((self.mode == 0 and (end_Thread == 0))):
                self.mylcd.lcd_display_string("Door Locked", 2)
                self.update()
            #self.mylcd.lcd_clear()
            while ((self.mode == 1) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Door Unlocked", 2)
                self.update()
            #self.mylcd.lcd_clear()
            while ((self.mode == 2) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Held Open", 2)
                self.update()
            #self.mylcd.lcd_clear()
            while ((self.mode == 3) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Access Denied", 2)
                self.update()
            self.mylcd.lcd_clear()
            while ((self.mode == 4) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Away Mode", 2)
                self.update()
            #self.mylcd.lcd_clear()
            while ((self.mode == 5) and (end_Thread == 0)):
                tag_name = sql_fetch("tag_name", self.door)
                dsp_txt = "Swipe " + str(tag_name)
                self.mylcd.lcd_display_string(dsp_txt, 2)
                self.update()
            #self.mylcd.lcd_clear()
            while ((self.mode == 6) and (end_Thread == 0)):
                self.mylcd.lcd_display_string("Swipe to Remove", 2)
                self.update()
            #self.mylcd.lcd_clear()    
            time.sleep(.2)    
            
        self.mylcd_clear()
        self.update()
        self.mylcd.lcd_display_string("Exiting", 2)

    def update(self):
        time.sleep(.2)
        self.mode = sql_fetch("mode", self.door)
        dsp_time = time.strftime("%-I:%M:%S %p")
        self.mylcd.lcd_display_string(str(dsp_time), 1)
        
class Menu_System(threading.Thread):
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
    def run(self):
        global end_Thread
        
        while (end_Thread == 0):
            time.sleep(.5)
            print(screen_print())
            print("\nAdd, Remove, Open, Close, Cancel, Quit")
            action = input("What do you want to do: ")

            if (action == "Add"):
                name = input("Who is this tag for?")
                try:
                    sql_update("tag_name", name, self.door, "Add Tag")
                    sql_update("mode", 5, self.door, "Add Tag")
                except:
                    print("Error")
            elif (action == "Remove"):
                sql_update("mode", 6, self.door, "Remove Tag")
            elif (action == "Open"):
                sec = input("How Long (sec)?")
                if (sec == "99"):
                    print("Sec = 99")
                    Door_Open(sec, 2)
                else:
                    Door_Open(sec, 1)
            elif (action == "Close"):
                Door_Close()
            elif (action == "Cancel"):
                if (sql_fetch('mode', self.door) != 1):
                    sql_update('mode', 0, self.door, "Cancel")
                    print("Canceling Action")
                    
                else:
                    print("No Action to Cancel")
            elif (action == "Quit"):
                print("Exiting")
                Alert("Door Security Exit")
                end_Thread = 1
            action = 0
        GPIO.cleanup()
        
def Door_Open(sec, mode):
    global led_state
    what_door = 'Front'
    sec = float(sec)
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(37, GPIO.OUT) ## Relay SETUP
    
    try:
        GPIO.output(37, GPIO.HIGH)
        sql_update("mode", mode, what_door, "Unlocked Door")
    except:
        Alert('Error Opening Door')
    else:
        Alert('Door Unlocked')
        
        if (sec != 99):
            time.sleep(sec)
            Door_Close()
    
def Door_Close():
    what_door = 'Front'
    mode = sql_fetch("mode", what_door)
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(37, GPIO.OUT) ## Relay SETUP
    try:
        GPIO.output(37, GPIO.LOW)
    except:
        Alert('Error Locking Door')
    else:
        if (mode != 4):
            sql_update("mode", 0, what_door, "Locked Door")
        Alert('Door Locked')
        
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
def sql_update(field, value, door, msg):
    ## Connect to SQL DB
    try:
        conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
        c = conn.cursor (MySQLdb.cursors.DictCursor)
    except:
        log("Error Connecting to DB")
    ## Create SQL and Update settings table
    try:
        sql = ("UPDATE settings SET " + str(field) + " = '" + str(value) + "' WHERE door = '" + str(door) + "'")
        c.execute(sql)
        conn.commit()
        #log(("Changed " + str(field) + " to " + str(value) + " for zone " + str(zone)))
    except:
        error = ("Error in SQL Update - " + msg + sql)
        log(error)
        
def sql_update_t_stat(field, value, zone, msg):
    ## Connect to SQL DB
    try:
        conn = MySQLdb.connect("192.168.68.112","pi","python","thermostat", port=3306 )
        c = conn.cursor (MySQLdb.cursors.DictCursor)
    except:
        log("Error Connecting to DB")
    ## Create SQL and Update settings table
    try:
        sql = ("UPDATE settings SET " + str(field) + " = '" + str(value) + "' WHERE zone = '" + str(zone) + "'")
        c.execute(sql)
        conn.commit()
        #log(("Changed " + str(field) + " to " + str(value) + " for zone " + str(zone)))
    except:
        error = ("Error in SQL Update - " + msg)
        log(error)


def sql_fetch_t_stat(field, zone):
    ## Connect to SQL DB
    try:
        conn = MySQLdb.connect("192.168.68.112","pi","python","thermostat", port=3306 )
        c = conn.cursor (MySQLdb.cursors.DictCursor)
    except:
        error = ("Error in SQL_Fetch_t_stat with DB Connect")
        log(error)
    else:
        sql = ("SELECT " + str(field) + " FROM settings WHERE zone = '" + str(zone) + "'")
        c.execute(sql)
        row = c.fetchone()
        return(row[field])
    
def sql_fetch(field, door):
    ## Connect to SQL DB
    try:
        conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
        c = conn.cursor (MySQLdb.cursors.DictCursor)
    except:
        error = ("Error in SQL_Fetch with DB Connect")
        log(error)
    else:
        sql = ("SELECT " + str(field) + " FROM settings WHERE door = '" + str(door) + "'")
        c.execute(sql)
        row = c.fetchone()
        return(row[field])
  

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

Door_Close()

GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
GPIO.setup(7, GPIO.IN, pull_up_down=GPIO.PUD_UP)

while (end_Thread == 0):
    input_state = GPIO.input(7)
    if (input_state == False):
        mode = sql_fetch("mode", "Front")
      
        if (mode == 0):
        
            try:
                Door_Open(99, 2)
            except:
                log("Failed to Set Mode in Button Unlock")
            else:
                sql_update("mode", 2, door, "Unlock Via Button")
                print("After Door Open")
                
                    
        elif(mode == 2):
                try:
                    sql_update("mode", 0, door, "Unlock Via Button")
                except:
                    log("Failed to Set Mode in Button Unlock")
                else:
                    Door_Close()
    


    time.sleep(.2)
    
