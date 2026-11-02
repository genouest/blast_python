#!/bin/bash
set -e

function run_scripts () {
	SCRIPTS_DIR="/scripts/$1.d"
	SCRIPT_FILES_PATTERN="^${SCRIPTS_DIR}/[0-9][0-9][a-zA-Z0-9_-]+$"
	SCRIPTS=$(find "$SCRIPTS_DIR" -type f -uid 0 -executable -regex "$SCRIPT_FILES_PATTERN" | sort)
	if [ -n "$SCRIPTS" ] ; then
		echo "=>> $1-scripts:"
	    for script in $SCRIPTS ; do
	        echo "=> $script"
			. "$script"
	    done
	fi
}

run_scripts pre-launch
# Drop privileges and launch the webserver as the app user so that DRMAA/slurm
# jobs are submitted under that user.
exec setpriv --reuid "$APP_USER" --regid "$APP_GROUP" --init-groups \
    uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
