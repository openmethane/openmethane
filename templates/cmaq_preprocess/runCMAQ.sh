#!/bin/bash

## set important parameters

## dates (format = YYYYMMDD)
STDATE=TEMPLATE
ENDATE=TEMPLATE
# domains=(d01 d02 d03)
domains=(TEMPLATE)
cmaqDir=TEMPLATE
ctmDir=TEMPLATE
doCompress=TEMPLATE
compressScript=TEMPLATE
run=TEMPLATE

if [ `echo -n $STDATE | wc -c` -eq 7 ] ; then
    SYEAR=`echo "$STDATE / 1000" | bc`
    SJDAY=`echo "($STDATE % 1000) - 1" | bc`
    SDAY=`date -u -d "$SYEAR-01-01 + $SJDAY days UTC" '+%s'`
    SYYYYMMDD=`date -u -d "$SYEAR-01-01 + $SJDAY days UTC" '+%Y%m%d'`
    SYYYYMMDDHH=`date -u -d "$SYEAR-01-01 + $SJDAY days UTC" '+%Y%m%d%H'`
    EYEAR=`echo "$ENDATE / 1000" | bc`
    EJDAY=`echo "($ENDATE % 1000) - 1" | bc`
    EDAY=`date -u -d "$EYEAR-01-01 + $EJDAY days UTC" '+%s'`
else
    SYEAR=`echo $STDATE | cut -c1-4`
    SJDAY=`date -u +%j -d "$STDATE UTC"`
    SJDAY=`echo $SJDAY-1 | bc`
    SDAY=`date  -u -d "$STDATE UTC" '+%s'`
    SYYYYMMDD=$STDATE
    SYYYYMMDDHH=`echo "${STDATE}00"`
    EYEAR=`echo $ENDATE | cut -c1-4`
    EJDAY=`date -u +%j -d "$ENDATE UTC"`
    EJDAY=`echo $EJDAY-1 | bc`
    EDAY=`date -u -d "$ENDATE UTC" '+%s'`
fi

firstDom="${domains[0]}"
lastDom="${domains[${#domains[@]}-1]}"
nsecperday=`echo 24*60*60 | bc`
modelDir=$cmaqDir/scripts/cctm

for dom in "${domains[@]}" ; do
    DAY=$SDAY

    while [ $DAY -le $EDAY ] ; do
	## get the dates formatted correctly
	YEAR=`date -u -d "1970-01-01 + $DAY seconds UTC" '+%Y'`
	JDAY=`date -u -d "1970-01-01 + $DAY seconds UTC" '+%j'`
	YYYYMMDD=`date -u -d "1970-01-01 + $DAY seconds UTC" '+%Y%m%d'`
	YYYYMMDDdashed=`date -u -d "1970-01-01 + $DAY seconds UTC" '+%Y-%m-%d'`
	YYYYMMDDHH=`date -u -d "1970-01-01 + $DAY seconds UTC" '+%Y%m%d%H'`
	DATE=`echo $YEAR*1000 + $JDAY| bc`
	## print the date info
	echo "DAY = $DAY, EDAY = $EDAY, DATE=$DATE"

	## place where output will go
	outfolder=$ctmDir/$YYYYMMDDdashed/$dom
	
	## run BCON (not for all grids)
	if [ $dom != $firstDom ] ; then
	    bconScript=$outfolder/run.bcon_${dom}_${YYYYMMDD}
	    chmod u+x $bconScript
	    outfile=$bconScript.output.txt
	    timenow=`date '+%F %T'`
	    echo "$timenow: $bconScript &>$outfile" 
	    time $bconScript &>$outfile
	    ## check that it ran successfully
	    successCount=`grep -c 'Program  BCON completed successfully' $outfile`
	    if [ "$successCount" != "1" ] ; then
		echo "Failure in BCON - date = $YYYYMMDD, dom = $dom"
		echo "Run script = $bconScript"
		echo "Output script = $outfile"
		exit -1
	    fi
	fi

	## run CCTM
	cctmScript=$outfolder/run.cctm_${dom}_${YYYYMMDD}
	chmod u+x $cctmScript
	outfile=$cctmScript.output.txt
	timenow=`date '+%F %T'`
	echo "$timenow: $cctmScript &>$outfile" 
	time $cctmScript &>$outfile
	## check that it ran successfully
	successCount=`grep -c 'Program completed successfully' $outfile`
	if [ "$successCount" != "1" ] ; then
	    echo "Failure in CCTM - date = $YYYYMMDD, dom = $dom"
	    echo "Run script = $cctmScript"
	    echo "Output script = $outfile"
	    exit -1
	fi

	## compress, tar, move log-files from model folder to output folder
	THISDIR=`pwd`
	cd ${modelDir}
	echo "tar cfz ${outfolder}/logfiles_${dom}_${YYYYMMDD}.tar.gz CTM_LOG_*.${run}_${YYYYMMDD}"
	tar cfz ${outfolder}/logfiles_${dom}_${YYYYMMDD}.tar.gz CTM_LOG_*.${run}_${YYYYMMDD}
	echo "rm -f CTM_LOG_*.${run}_${YYYYMMDD}"
	rm -f CTM_LOG_*.${run}_${YYYYMMDD}
	cd $THISDIR

        ## ## compress
	if [ "$doCompress" == "true" ] ; then
	    echo "$compressScript $outfolder"
	    $compressScript $outfolder
	fi

	## increment the date
        DAY=$((DAY+$nsecperday))
	
    done
    
done

