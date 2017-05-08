#!/bin/bash
#
# Deploy the bentv_ui.py and bentv.sh scripts to the /home/pi folder
# on the hosts identified in hostlist, rebooting each host after deployment.
#
hostlist=('192.168.0.61' '192.168.0.65' '192.168.0.66')
echo hostlist = ${hostlist[@]}
for host in ${hostlist[@]}
do
    echo Deploying to $host.....
    rcp  bentv_ui.py pi@$host:/home/pi
    rcp  bentv.sh pi@$host:/home/pi
    echo Rebooting $host.....
    rsh $host -l pi sudo shutdown -r now
done
    
