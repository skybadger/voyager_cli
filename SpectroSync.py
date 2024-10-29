'''
References: 
https://github.com/agalasso/phd2client
https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring#available-methods
https://github.com/electrosparkz/voyager_python_client
file:///C:/Program%20Files%20(x86)/Voyager/VoyagerAS.pdf

Concept of operations: 
Use a platesolving pointing camera on scope 2  
Use a guide camera imaging the spectroscope guide image and slit on scope 1
Use a main camera imaging the spectra on scope 1

Point to target on scope 2 


Assumptions
Assumption 0 - the pointing scope and the spectrometer scope can be fine aligned to put the target star near the guide cam slit. 
Assumption 1 - sticky lock already applied to place guide location over slit centre. 
Assumption 2 - Can set current position for V#2 so that imaging headers are correctly populated. 
Assumption 3 - use primary instance of Voyager in Advanced Robotarget mode to provide target lists or use survey mode in normal Voyager. 


Clients connect to PHD2 on TCP port 4400. When multiple PHD instances are running, each instance listens on successive port numbers (4401, 4402, ...).
PHD allows multiple clients to establish connections simultaneously.
When a client establishes a connection, PHD sends a series of event notification messages to the client (see #Initial_Messages). Then, as guiding events take place in PHD, notification messages are sent to all connected clients.

Pre req: 
- Have Voyager instance 1 (v#1) set to control guide cam platesolving ( pointing ) camera, guider on main telescope, mount and other ancillaries
- Have Voyager istance 2 (v#2) set to control imaging camera which is taking spectra on the spectroscope. 
                                 
Process: 
Connect to V#1 - initialise profile and connect
import Connect to v#2 - initialise profile and connect
Connect to guider - also connected in profile for V1 ? problem ?

point to target
solve for location 
precision point 
connect to guider 
set exposure time
get guide image 
solve guide image using platesolve camera outcome as hint.
calculate difference of centres between platesolving cam and guide cam
apply difference to guider centre to select target star in guider 

apply sticky lock to bring target star to slit 

update V2 position  - can set via telling it to move simulated mount to target RA, DEC 

'''
#import requests - needs download 
import argparse
import time
from pprint import pprint
import os
import io
import json
import base64
import logging
#import pillow

from voyager_api import VoyagerClient, setup_logging
#from websocket_server import WebsocketServer
from guider import Guider, GuiderException

#handler to receive all dashboard status signals. 
def handle_control_data(message, *args, **kwargs):
    #add handling exec functions. 
    datastruct = {
        'mount': {
            'alt': message['MNTALT'],
            'az': message['MNTAZ'],
            'conn': message['MNTCONN'],
            'dec': message['MNTDEC'],
            'ra': message['MNTRA'],
            'slew': message['MNTSLEW'],
            'track': message['MNTTRACK'],
            'park': message['MNTPARK'],
            'pier': message['MNTPIER'],
            'meridian': message['MNTTFLIP']
        },
        'setup': {
            'conn': message['SETUPCONN'],
            'ds': message['RUNDS'],
            'seq': message['RUNSEQ'],
            'voyager': _map_voystat(message['VOYSTAT'])

        },
        'sequence': {
            'end': message['SEQEND'],
            'remain': message['SEQREMAIN'],
            'start': message['SEQSTART'],
            'name': message['SEQNAME']
        },
        'camera': {
            'conn': message['CCDCONN'],
            'cooling': message['CCDCOOL'],
            'coolpower': message['CCDPOW'],
            'coolset': message['CCDSETP'],
            'status': _map_ccdstat(message['CCDSTAT']),
            'temp': message['CCDTEMP']
        },
        'focuser': {
            'conn': message['AFCONN'],
            'pos': message['AFPOS'],
            'temp': message['AFTEMP']
        },
        'guider': {
            'conn': message['GUIDECONN'],
            'status': _map_guidestat(message['GUIDESTAT']),
            'x': message['GUIDEX'],
            'y': message['GUIDEY'],
        },

    }
    print ( datastruct )
    return datastruct

#function to register and act on the pointing complete outcomes 
def pointingCompleteHandler ( ) : 
    return

vclient1 = None
vclient2 = None
phdClient = None

#target data
solvedRA = 0.0
solvedDec = 0.0
targetRA = 0.0
targetDec = 0.0

#Guider data 
guiderDiffRA = 0.0
guiderDiffDec = 0.0
guiderImageSizeX = 0
guiderImageSizeY = 0
guiderSolvedRA = 0.0
guideSolverDEC = 0.0


def readConfig():      
    parser = argparse.ArgumentParser(prog="SpectroSync", 
                                    description="""
            This app is to help synchronise two telescopes managed by instance of Voyager so you can use a spectrometer on one scope and a platesolver for pointing on the other.
            It requires instance #1 to provide the platesolving main camera on the 2nd telescope and the slit guider on the telescope with the spectrometer.  
            It requires instance #2 to provide the spectrometer imaging camera only, configured with a simulator telescope mount. 
            Usage: python SpectroSync.py """)

    #Voyager 1 access details
    parser.add_argument("-hv1",  "--hostnamev1", help="provide the hostname of the voyager #1 instance in quotes e.g.'\"name\"' ", type=str, default="localhost" )
    parser.add_argument("-pv1",  "--portv1",     help="Port of voyager server api for instance 2", type=int, default=5950)
    parser.add_argument("-uv1",  "--usernamev1", help="USername for Voyager server account",type=str, default="skybadger" )
    parser.add_argument("-pwv1", "--passwordv1", help="password of access key to API for instance 2", type=str, default="" )
    #Voyager 2 access details
    parser.add_argument("-hv2",  "--hostnamev2", help="provide the hostname of the voyager #2 instance in quotes e.g. '\"name\"' ", type=str, default="localhost")#assume use of dns names to start with 
    parser.add_argument("-pv2",  "--portv2",     help="Port of voyager server api for instance 2", type=int,  default=5951)
    parser.add_argument("-uv2",  "--usernamev2", help="Username for Voyager server account",type=str,  default="skybadger" )
    parser.add_argument("-pwv2", "--passwordv2", help="password of access key to API for instance 2", type=str,  default="" )
    parser.add_argument("-tgl",  "--targetList", type=str,  default=["alplyr", "alpand", "gamcas"] )

    #Phd2 guide port
    parser.add_argument("-gp", "--guideport", help="port for Phd2 instance (assumed local to voyager instance #1)", type=int, default=4400)

    #platesolver command line 
    # Ex: '-f "C:\Users\mharrison\Documents\Voyager\FIT\SyncVoyager_20231110_185255.fit" -fov 0.358222 -z 0 -s 500 -r 30 -ra 22.194631 -spd 76.993297 -m 1.5'
    parser.add_argument("-ps", "--platesolver", help="Required to be local, e.g. 'c:\\program files\\astap\\astapcli.exe -f \"temp.fit\" -fov 0.358222 -z 0 -s 500 -r 30 -ra 22.194631 -spd 76.993297 -m 1.5''", type=str, default="")

    #Help
    #parser.add_argument("-h", "--help", help="output user help", type=str, default="this is the help string" )

    args = parser.parse_args()
    #check args make sense
    print( "checking", args)

    print ( "Args received:", args)

    if ( len(args.passwordv1) == 0 or len( args.usernamev1 ) == 0 ) :
        print("Error: No accountinfo supplied to use as Voyager basic access tokens ")
    return args

def main():
    logger = logging.getLogger(__name__)
    setup_logging(True, False)

    config = readConfig()

    vclient1 = VoyagerClient( host=config.hostnamev1, port=config.portv1 )
    response = vclient1.start()
    vclient1.cmd.set_logs('enable')
    vclient1.cmd.set_dashboard('enable')

    #According to the Server API doc this needs encoding in utf-8 as octet then base64
    encodedAuth = config.usernamev1 + ':' + config.passwordv1
    print ( "Base:", encodedAuth )
    encodedAuth =  encodedAuth.encode()
    #still a string but in b'' format 
    print("octet:", encodedAuth)
    encodedAuth = base64.urlsafe_b64encode( encodedAuth )
    print( "encoded authentication data:", encodedAuth)
    
    response = vclient1.add_handler('ControlData', handle_control_data, server=config.hostnamev1 )

    #connect profile devices - especially the configured and calibrated phd2.
    response = json.dumps( vclient1.cmd.connect_setup() )
    print( response )
    
    #Having connected, now need to connect to the guider which has already been opened and activated by Voyager
    guider = Guider( config.hostnamev1 )
    guider.Connect()

    #get the profile information in support of the plate solving later. 

    #determine and save current guide state - looping, nothing or capturing ? 
    #status = guider.GetStatus()
    #lockPos = guider.getLockPosition() #null if not set or a tuple if set. 
    #scale = guider.getPixelScale() # \" per pixel 

    guider.Pause()

    #Now ensure we know where we are pointing- use target list and Voyager  
    vclient1.cmd.mount_action( "unpark")
    #Set target to object to be found by local planetarium  - expect result of FOUND=1 
    output = vclient1.send_command("RemoteSearchTarget", params={"Name": config.targetList[0], "SearchType":0} )
    print ( output )
    #acquire and solve actual position using fine pointing
    targetDescriptor = { "Name": output["Name"], "RAJ2000":output["RAJ2000"], "DECJ2000": output["DECJ2000"] }
    output = vclient1.send_command("RemotePrecisePointTarget", 
                                   params={"IsText": False, "RA": output["RAJ2000"], "DEC": output["DECJ2000"], "RAText":"", "DECText":"", "Parallelized" : False } )
    print( json.dumps(output) ) 

    #Set guide state to capture a long exposure image 
    #this approach means the python has to be on the same machine as the phd host save to the same share drive path.  

    guider.Call("capture_single_frame", param=[30000] )
    filename = guider.SaveImage( )

    #solve the guide image
    #call out to use ASTAP with the appropriate image parameters
    #work out where we think we are pointing 


    #Solve the star field and determine the centre of the field. 

    #Calc the offset between pointing camera centre and guide camera centre so we know where we think the target star is in the guider fov. 

    #set the guide star as the star in the locus of centre + offset assuming camera is aligned to telescope axiis. 
    #set sticky move to centre.
    #wait until settled 
    #repeat until error is minimal 

    # This will do a precise pointing through voyager, including the plate solve and sync.
    # Action RemotePrecisePointTarget defined on page 46/47 of API guide. 
    # ActionResult in the returned data will be one of the 4 items described on that page to know the status of the action.
    output = vclient1.cmd.precise_point_target(ra=12.01, dec=30.15)  
    print ( output )
    output = vclient1.cmd.disconnect_setup()
    print ( output )
    #check for connection complete or partial failures

    #connect again in case of failures. 
    output = vclient1.cmd.connect_setup()
    print ( output )

    vclient1.send_command('RemoteSetupDisconnect')


    vclient1.close() 


if __name__ == "__main__":
    main()
    