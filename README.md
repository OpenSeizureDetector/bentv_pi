bentv
=====

BenTV - a raspberry pi based system for monitoring a vulnerable person by
cctv and the OpenSeizureDetector seizure detector.

The majority of the screen shows the video stream from an IP video camera.
The bottom section of the screen shows the status of the OpenSeizureDetector
seizure detection system, changing colour if a warning or alarm is initiated.

[[https://github.com/openseizuredetector/bentv_pi/blob/master/imgages/screenshot.png|alt=screenshot]]
 

Installation
 * Copy the contents of the repository into /home/pi on the Raspberry Pi
 file system.
 * add /home/pi/bentv.sh and home/pi/bentv_ui.py to /etc/rc.local so they
 run on start-up.
 * edit config.ini to match your system set up - in particular the IP address
 of the OpenSeizureDetector phone.


