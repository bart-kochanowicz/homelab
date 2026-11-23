#!/bin/sh
# Sends one archived front-door snapshot to the person detector that runs in the same pod (loopback only)
# and prints its JSON answer. Called by the front_door_person_detect shell command with the file as the only
# argument. Home Assistant runs a templated shell command without a shell, so the logic lives here.
# Exit codes: 2 = not an archive file name, 3 = the file did not appear, otherwise curl's.
f=${1:-}
case "$f" in
    /config/media/front-door/????-??-??_??-??-??.jpg) ;;
    *) exit 2 ;;
esac
# In a case pattern `?` also matches `/`, so refuse a name that leaves the archive directory.
case "${f#/config/media/front-door/}" in
    */*) exit 2 ;;
esac
# The archive automation writes the file; wait for it for up to ten seconds, in tenths, and then until its size
# stops changing, so a half-written picture is never sent.
i=0
while [ "$i" -lt 100 ]; do
    [ -s "$f" ] && break
    i=$((i + 1))
    sleep 0.1
done
[ -s "$f" ] || exit 3
size=$(wc -c < "$f")
while [ "$i" -lt 100 ]; do
    sleep 0.1
    i=$((i + 1))
    now=$(wc -c < "$f")
    [ "$now" = "$size" ] && break
    size=$now
done
# detect <detector> <minimum confidence>: the detector's JSON answer for the picture.
detect() {
    {
        printf '{"detector_name":"%s","detect":{"person":%s},"data":"' "$1" "$2"
        base64 -w0 "$f"
        printf '"}'
    } | curl -sf -m 30 -X POST -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8089/detect
}
# The fast detector first: a person it reports at 60 % or more is the answer. Otherwise the accurate one decides.
answer=$(detect fast 60) || answer=
case "$answer" in
    *'"label":"person"'*) printf '%s\n' "$answer" ;;
    *) detect person 50 ;;
esac
