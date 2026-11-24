#!/bin/sh
# Moves one archived front-door snapshot in which the detector found nobody into the archive's no-person folder,
# so the events panel (which lists only the archive's own files) shows the pictures with a person. The folder
# stays browsable under Media to look for a missed person. Called by the front_door_snapshot_set_aside shell
# command with the file as the only argument. Exit codes: 2 = not an archive file name, otherwise mv's.
f=${1:-}
case "$f" in
    /config/media/front-door/????-??-??_??-??-??.jpg) ;;
    *) exit 2 ;;
esac
# In a case pattern `?` also matches `/`, so refuse a name that leaves the archive directory.
case "${f#/config/media/front-door/}" in
    */*) exit 2 ;;
esac
mkdir -p /config/media/front-door/no-person && mv -f "$f" /config/media/front-door/no-person/
