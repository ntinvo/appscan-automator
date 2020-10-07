#!/bin/bash

#########################################
#    MODIFIED   (MM/DD/YY)              #
#    ntinvo      02/29/20 - Creation    #
#########################################

DB2_CONTAINER=${1}


echo `date`
echo -e "DB2 container ${DB2_CONTAINER}"


# check database connection
function check_database_connection() {
    STARTTIME=$(date +%s)
    echo -e "\nWaiting for DB2..."
    while [[ ${test:-0} -lt 5 ]]; do
        $(docker exec $DB2_CONTAINER /bin/bash -c '[ -f /dev/shm/.db_ready ]') && test=$((test+1)) || unset test
        [ ${cnt:-0} -gt 30 ] && echo "." && unset cnt || echo -n "."
        cnt=$((cnt+1))
        sleep 1
    done
    echo -e "\nDB2 started in $(($(($(date +%s) - $STARTTIME))/60)):$(($(($(date +%s) - $STARTTIME))%60)) minutes"
}


check_database_connection 

if [ $? -eq 0 ]; then
    echo "DB2 started SUCCESSFULLY!!!"
else
   echo "DB2 started UNSUCCESSFULLY!!!"
   exit 1
fi