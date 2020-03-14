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

relaypin = 37
red_pin = 38
green_pin = 40
white_pin = 36
blue_pin = 32
door = "Front"
end_Thread=0

class Cards(threading.Thread):
    ## Thread actively watches for scanned cards
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
    def run(self):
        global end_Thread
        what_door = self.door
        
        while True:
            try:            
                reader = SimpleMFRC522() ## Setup RFID Reader
                tag_id, text = reader.read() ## Watches for Cards
            except:
                log("Error With Card Reader")
            else:
                mode = sql_fetch('mode', what_door) ## Find Current Mode
                tag_name = sql_fetch('tag_name', what_door)
                ## Check for Action from UI
                if ((mode == 1) or (mode == 7)): ## Mode 1, Normal - Check for access after scan
                    
                    Access(tag_id, text)
                    
                elif (mode == 6): ## Mode 6, Open (buttton pushed and opened door)
                    ## Will set away in thermostat after scan
                    sql_update_t_stat("holdtemp", 58, "Living", "Setting Home AWAY")
                    sql_update_t_stat("settemp", 58, "Upstairs", "Setting Home AWAY")
                    sql_update_t_stat("settemp", 58, "Kitchen", "Setting Home AWAY")
                    sql_update_t_stat("hold", 1, "Living", "Setting Home AWAY")
                    sql_update_t_stat("hold", 1, "Control", "Setting Home AWAY")
                    ## Set Mode to Normal (1)
                    sql_update("mode", 1, what_door, "Scan to set away")
                    # Lock Door
                    Door_Close()
                    
                elif (mode == 4): ## Add Tag
                    reader.write(tag_name)
                    Add(tag_id, tag_name)
                    sql_update("mode", 1, what_door, "Done Add")
                    msg = ("Added - " + tag_name)
                    log(msg)
                    
                elif (mode == 5): ## Remove Tag
                    Remove(tag_id, text)
                    sql_update("mode", 1, what_door, "Done Remove")
                    msg = ("Removed - " + str(text))
                    log(msg)
                    time.sleep(3)

                time.sleep(1)


class Menu_System(threading.Thread):
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
    def run(self):
        global end_Thread
        what_door = self.door
        
        while (end_Thread == 0):
            time.sleep(.5)
            print(screen_print())
            print("\nAdd, Remove, Open, Close, Cancel, Quit")
            action = input("What do you want to do: ")

            if (action == "Add"):
                name = input("Who is this tag for?")
                try:
                    sql_update("tag_name", name, what_door, "Add Tag")
                    sql_update("mode", 4, what_door, "Add Tag")
                except:
                    print("Error")
            elif (action == "Remove"):
                sql_update("mode", 5, what_door, "Remove Tag")
            elif (action == "Open"):
                sec = input("How Long (sec)?")
                Door_Open(sec)
            elif (action == "Close"):
                Door_Close()
            elif (action == "Cancel"):
                if (sql_fetch('mode', what_door) != 1):
                    sql_update('mode', 1, what_door, "Cancel")
                    print("Canceling Action")
                    led_state = 1
                else:
                    print("No Action to Cancel")
            elif (action == "Quit"):
                print("Exiting")
                Alert("Door Security Exit")
                end_Thread = 1
            action = 0
        GPIO.cleanup()
class led_status(threading.Thread):
    def __init__(self, green_pin, red_pin, white_pin, blue_pin, door):
        threading.Thread.__init__(self)
        self.red = red_pin
        self.green = green_pin
        self.white = white_pin
        self.blue = blue_pin
        self.door = door
        ## Add time var to speed up responce, compare to time.now
    def run(self):

        ## GPIO SETUP
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.green, GPIO.OUT)
        GPIO.setup(self.white, GPIO.OUT)
        GPIO.setup(self.red, GPIO.OUT)
        GPIO.setup(self.blue, GPIO.OUT)
        GPIO.output(self.green, GPIO.LOW)
        GPIO.output(self.white, GPIO.LOW)
        GPIO.output(self.red, GPIO.LOW)
        GPIO.output(self.blue, GPIO.LOW)

        global end_Thread
        global led_state
        which_door = self.door
        now = time.time()

        while (end_Thread == 0):
            now = time.time()
            led_state = sql_fetch("mode",which_door)
            while ((led_state == 1) or (led_state == 6)): # Normal waiting for card swipe                            
                locked = sql_fetch("locked",which_door)
                if (locked == 1):
                    GPIO.output(self.green, GPIO.LOW)
                    GPIO.output(self.white, GPIO.HIGH)
                    time.sleep(.5)
                    led_state = sql_fetch("mode",which_door)
                    GPIO.output(self.white, GPIO.LOW)
                    time.sleep(.5)
                    led_state = sql_fetch("mode",which_door)
                if (locked == 0):
                    GPIO.output(self.green, GPIO.HIGH)
                    led_state = sql_fetch("mode",which_door)
                
            while ((led_state == 2) or (led_state == 6)): ## Door Unlocked
                GPIO.output(self.green, GPIO.HIGH)
                led_state = sql_fetch("mode",which_door)
                time.sleep(.1)
            while (led_state == 3): # Access Denied
                GPIO.output(self.red, GPIO.HIGH)
                time.sleep(.1)
                led_state = sql_fetch("mode",which_door)
                GPIO.output(self.red, GPIO.LOW)
                time.sleep(.1)
                led_state = sql_fetch("mode",which_door)
            while (led_state == 4): # Add Card
                GPIO.output(self.blue, GPIO.HIGH)
                time.sleep(.1)
                led_state = sql_fetch("mode",which_door)
                GPIO.output(self.blue, GPIO.LOW)
                time.sleep(.1)
                led_state = sql_fetch("mode",which_door)
            while (led_state == 5): # Remove Card
                GPIO.output(self.blue, GPIO.HIGH)
                time.sleep(.1)
                led_state = sql_fetch("mode",which_door)
                GPIO.output(self.blue, GPIO.LOW)
                time.sleep(.1)
                led_state = sql_fetch("mode",which_door)
            while (led_state == 7):
                GPIO.output(self.green, GPIO.LOW)
                GPIO.output(self.blue, GPIO.HIGH)
                GPIO.output(self.red, GPIO.HIGH)
                time.sleep(.05)
                led_state = sql_fetch("mode",which_door)
            GPIO.output(self.green, GPIO.LOW)
            GPIO.output(self.white, GPIO.LOW)
            GPIO.output(self.red, GPIO.LOW)
            GPIO.output(self.blue, GPIO.LOW)
        GPIO.cleanup()
class lcd_status(threading.Thread):
    def __init__(self, door):
        threading.Thread.__init__(self)
        self.door = door
    def run(self):

        global end_Thread
        now = time.time()
        mylcd = I2C_LCD_driver.lcd()
        which_door = self.door
        
        while (end_Thread == 0):
            mode = sql_fetch("mode", which_door)
            locked = sql_fetch("locked", which_door)
            mylcd.lcd_clear()
            while((mode == 1) or (mode == 6)):
                now_time = time.strftime("%-I:%M:%S %p")
                mylcd.lcd_display_string(str(now_time), 1)
                
                if(locked == 1):
                    mylcd.lcd_display_string("Door Locked", 2)
                elif((locked == 0) or (mode == 6)):
                    mylcd.lcd_display_string("Door Unlocked", 2)
                else:
                    print("Not 1 or 0")
                time.sleep(.05)
                mode = sql_fetch("mode", which_door)
                locked = sql_fetch("locked", which_door)
            mylcd.lcd_clear()
            while(mode == 2): ##Door Unlocked
                lcd_name = sql_fetch("tag_name", which_door)
                mylcd.lcd_display_string("Access Granted", 1)
                mylcd.lcd_display_string(lcd_name, 2)
                time.sleep(.05)
                mode = sql_fetch("mode", which_door)
            while(mode == 3): ## Access Denied
                lcd_name = sql_fetch("tag_name", which_door)
                mylcd.lcd_display_string("Access Denied", 1)
                time.sleep(.05)
                mode = sql_fetch("mode", which_door)
            while(mode == 4): ## Add Tag
                lcd_name = sql_fetch("tag_name", which_door)
                mylcd.lcd_display_string("Swipe Tag", 1)
                mylcd.lcd_display_string(lcd_name, 2)
                time.sleep(.05)
                mode = sql_fetch("mode", which_door)
            while(mode == 5): ## Remove Tag
                mylcd.lcd_display_string("Swipe Tag", 1)
                mylcd.lcd_display_string("to Remove", 2)
                time.sleep(.05)
                mode = sql_fetch("mode", which_door)
            while(mode == 7):
                now_time = time.strftime("%-I:%M:%S %p")
                mylcd.lcd_display_string(str(now_time), 1)
                
                if(locked == 1):
                    mylcd.lcd_display_string("Away Mode", 2)
                
                time.sleep(.05)
                mode = sql_fetch("mode", which_door)
                locked = sql_fetch("locked", which_door)

def Add(tag_id, name):    
    reader = SimpleMFRC522()
    print("Adding")
    conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
    c = conn.cursor (MySQLdb.cursors.DictCursor)
    sql = ("INSERT into rfid (tag_id, tag_name) VALUES (" + str(tag_id) + ", '" + str(name) + "')")
    c.execute(sql)
    conn.commit()
    print("Added - " + str(name))
    sql_update("mode", 1, "Front", "Remove Tag")

def Remove(tag_id, name):
    print("Removing")
    conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
    c = conn.cursor (MySQLdb.cursors.DictCursor)
    sql = ("DELETE FROM rfid WHERE tag_id = '" + str(tag_id) + "'")
    c.execute(sql)
    conn.commit()
    print("Removed - " + str(name))


    reader = SimpleMFRC522()
    tag_id, text = reader.read()
    print("Removing Tag for: " + str(text))
    conn = MySQLdb.connect("192.168.68.112","pi","python","doorlock", port=3306 )
    c = conn.cursor (MySQLdb.cursors.DictCursor)
    sql = ("DELETE FROM rfid WHERE tag_id = '" + str(tag_id) + "'")
    c.execute(sql)
    conn.commit()
    print("Removed")
    sql_update("mode", 1, "Front", "Remove Tag")

def Access(tag_id, name):
    print("Access Func.")
    what_door = "Front"
    mode = sql_fetch("mode", what_door)
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
            if (mode == 7):
                sql_update_t_stat("hold", 0, "Living", "Setting Home AWAY")
                sql_update_t_stat("settemp", 62, "Kitchen", "Setting Home AWAY")
                sql_update_t_stat("settemp", 58, "Upstairs", "Setting Home AWAY")
                sql_update_t_stat("hold", 0, "Control", "Setting Home AWAY")
            sql_update("mode", 2, what_door, "Access Granted")
            sql_update("tag_name", name, what_door, "Access Granted")
            Door_Open(10)
            sql_update("mode", 1, what_door, "Access Granted")
            
        elif row == None:
            print("Access Denied")
            sql_update("mode", 3, what_door, "Access Denied")
            time.sleep(5)
            sql_update("mode", 1, what_door, "Access Denied")
def Door_Open(sec):
    global led_state
    what_door = 'Front'
    sec = float(sec)
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(37, GPIO.OUT) ## Relay SETUP
    try:
        GPIO.output(37, GPIO.HIGH)
        led_state = 2
        relay_State = 1
    except:
        Alert('Error Opening Door')
    else:
        sql_update("Locked", 0, what_door, "Unlocked Door")
        Alert('Door Unlocked')
        
        if(sec != 99):
            time.sleep(sec)
            Door_Close()
    
def Door_Close():

    what_door = 'Front'
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(37, GPIO.OUT) ## Relay SETUP
    try:
        GPIO.output(37, GPIO.LOW)
    except:
        Alert('Error Locking Door')
    else:
        sql_update("locked", 1, what_door, "Unlocked Door")
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
                Door_Open(99)
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
    


## Reset System on startup
Door_Close()
sql_update("mode", 1, door, "Startup")

## Setup Push Button
GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
GPIO.setup(7, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    
        

    
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

    led_status = led_status(green_pin, red_pin, white_pin, blue_pin, door)
    led_status.start()
except:
    log("Error Starting Led Status")
## Start LCD Manager
try:

    lcd_status = lcd_status(door)
    lcd_status.start()
except:
    log("Error Starting LCD Status")





## Main While Loop
while (end_Thread == 0):
    input_state = GPIO.input(7)
    if (input_state == False):
        mode = sql_fetch("mode", "Front")
        locked = sql_fetch("locked", "Front")
        if (mode == 1):
            if(locked == 1):
                try:
                    Door_Open(99)
                except:
                    log("Failed to Set Mode in Button Unlock")
                else:
                    sql_update("mode", 6, door, "Unlock Via Button")
                    print("After Door Open")
                    
                    
        elif(mode == 6):
                try:
                    sql_update("mode", 1, door, "Unlock Via Button")
                except:
                    log("Failed to Set Mode in Button Unlock")
                else:
                    Door_Close()
    


    time.sleep(.3)


cards.join()
led_status.join()


## TO DO
## Add LED, both wire and Code
## Change all functions to include try/except/else statements
