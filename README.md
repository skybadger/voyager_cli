# voyager_python_client
Python client for interacting with the Voyager Astrophotography application server

In this intial case the client is trying to setup the app for use with a spectrograph. A spectrogroph contains at least 2 cameras and 3 might make life easier. 

The first is for the spectra acquisition 

The second is for the gyuiding 

The third might be used for initial pointing and fine-pointing as long as it remains precisely aligned or can be positionally calibrated against the guider camaera. 

The 2-camera solution here is to use the guider for positional solving as long as a long exposure captures enough stars in teh limited field of view. The FOV is limited since the finder on the spectrograph is in on-axis guider mode not a separate telescope. Due to the small sensor the FOV is limited to something like 10'x7'  at 2000mm focal length. Hence the reason a third camera makes life easier. 

Voyager itself does not support this number of cameras used at once in a single software instance

Voyager does support an array mode across multiple instances but this is intended for all cameras to be synchronised imaging a target not for different purposes. 


# Dependencies. 

The Voyager-api code is from ... https://github.com/electrosparkz/voyager_python_client

The phd guider access code is from ... https://github.com/agalasso/phd2client

voyager_api contains the VoyagerClient class, and contains (most) interactions with the Voyager API for sending commands, as well as the ability to add handlers for specific published messages as well. Example can be seen in the ws_server.py file.

ws_server is a websocket bridge that takes updates from the Voyager dashboard client messages, and formats them into a json structure to pass to any connected clients.

# Testing. 


