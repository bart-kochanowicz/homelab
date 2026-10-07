# UniFi port profiles

Access and trunk profiles reference logical network keys from the caller.
Access profiles reject tags; custom trunks exclude every LAN outside their
native/tagged set. Supply all managed and read-only LAN IDs.
Profiles have `prevent_destroy`; physical port assignment belongs to the caller.
