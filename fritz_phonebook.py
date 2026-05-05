"""
fritz_phonebook.py  –  FritzBox Phonebook → MicroSIP contacts.xml
===================================================================
An AppDaemon app for Home Assistant that reads the AVM FRITZ!Box
phonebook via TR-064 and writes a MicroSIP-compatible contacts.xml
to the Home Assistant /config/www/ directory, where it is served
by the built-in HA HTTP server and can be consumed by MicroSIP's
"Contacts URL" feature.

Scheduling:
    - Runs once immediately on AppDaemon startup.
    - Runs daily at the configured time (default: 04:30).

Requirements:
    - AppDaemon add-on (Home Assistant OS / Supervised)
    - fritzconnection Python package (add to AppDaemon add-on config
      under python_packages: [fritzconnection])
    - FRITZ!Box with TR-064 enabled:
      Heimnetz → Netzwerkeinstellungen → "Zugriff für Anwendungen zulassen"
    - A FRITZ!Box user account with "FRITZ!Box-Einstellungen" permission

Configuration (apps.yaml):
    fritz_phonebook:
      module: fritz_phonebook
      class: FritzPhonebook
      fritz_ip: "192.168.x.x"
      fritz_user: !secret fritz_user
      fritz_password: !secret fritz_password
      phonebook_id: 0                              # 0 = default phonebook
      output_path: "/config/www/microsip_contacts.xml"
      update_time: "04:30:00"

MicroSIP:
    Set "Contacts URL" in MicroSIP settings to:
    http://<HA-IP>:8123/local/microsip_contacts.xml

License:
    MIT License – Copyright (c) 2026 Michael Ionescu
"""

import hassapi as hass
import xml.etree.ElementTree as ET
import urllib.request
import os

# Set to True for verbose debug output in the AppDaemon log.
# Remember to set back to False after troubleshooting.
DEBUG = False


class FritzPhonebook(hass.Hass):
    """AppDaemon app that syncs the FRITZ!Box phonebook to MicroSIP."""

    def initialize(self):
        """
        Called by AppDaemon on startup and on app reload.
        Reads configuration from apps.yaml, triggers an immediate sync,
        and schedules the daily recurring sync.
        """
        fritz_ip       = self.args["fritz_ip"]
        fritz_user     = self.args.get("fritz_user", "")
        fritz_password = self.args["fritz_password"]
        phonebook_id   = int(self.args.get("phonebook_id", 0))
        output_path    = self.args["output_path"]
        update_time    = self.args.get("update_time", "04:30:00")

        # Run once immediately so the file exists right after (re)start
        self.update_phonebook(
            fritz_ip=fritz_ip,
            fritz_user=fritz_user,
            fritz_password=fritz_password,
            phonebook_id=phonebook_id,
            output_path=output_path,
        )

        # Schedule daily recurring update; pass all args via kwargs
        h, m, s = update_time.split(":")
        self.run_daily(
            self.daily_update,
            f"{h}:{m}:{s}",
            fritz_ip=fritz_ip,
            fritz_user=fritz_user,
            fritz_password=fritz_password,
            phonebook_id=phonebook_id,
            output_path=output_path,
        )
        self.log(f"FritzPhonebook: daily update scheduled at {update_time}.")

    def daily_update(self, kwargs):
        """Callback fired by the AppDaemon scheduler once per day."""
        self.update_phonebook(
            fritz_ip=kwargs["fritz_ip"],
            fritz_user=kwargs["fritz_user"],
            fritz_password=kwargs["fritz_password"],
            phonebook_id=kwargs["phonebook_id"],
            output_path=kwargs["output_path"],
        )

    def update_phonebook(self, fritz_ip, fritz_user, fritz_password,
                         phonebook_id, output_path):
        """
        Main sync routine:
          1. Connect to FRITZ!Box via TR-064 (fritzconnection).
          2. Call GetPhonebook to obtain a temporary download URL.
          3. Download the phonebook XML from that URL.
          4. Convert to MicroSIP contacts.xml format.
          5. Write the result to output_path inside /config/www/.

        Errors are caught and logged; an existing contacts.xml is
        left untouched when an error occurs.
        """
        try:
            self.log("FritzPhonebook: starting phonebook sync...")

            # Import here so AppDaemon can load the app even if
            # fritzconnection is not yet installed (will fail here, not
            # at module import time, giving a clearer error message).
            from fritzconnection import FritzConnection

            fc = FritzConnection(
                address=fritz_ip,
                # Pass None instead of empty string; fritzconnection will
                # then attempt to auto-detect the username (FRITZ!OS ≥ 7.24
                # requires an explicit username, so using !secret is preferred)
                user=fritz_user if fritz_user else None,
                password=fritz_password,
                use_cache=True,
            )
            self._debug(f"Connected to: {fc.modelname}")

            # TR-064 call: GetPhonebook returns a temporary URL that the
            # FRITZ!Box uses to serve the phonebook XML for download.
            result = fc.call_action(
                "X_AVM-DE_OnTel1",
                "GetPhonebook",
                NewPhonebookID=phonebook_id,
            )
            phonebook_url = result["NewPhonebookURL"]
            self._debug(f"Phonebook URL: {phonebook_url}")

            # Download the phonebook XML from the FRITZ!Box
            with urllib.request.urlopen(phonebook_url) as resp:
                fritz_xml_bytes = resp.read()
            self._debug(f"Phonebook XML downloaded: {len(fritz_xml_bytes)} bytes")

            # Convert FRITZ!Box XML schema → MicroSIP XML schema
            microsip_xml = self._convert(fritz_xml_bytes)

            # Ensure the target directory exists (e.g. /config/www/)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "wb") as f:
                f.write(microsip_xml)

            self.log(f"FritzPhonebook: contacts.xml updated → {output_path}")

        except Exception as e:
            self.log(f"FritzPhonebook: ERROR during update: {e}", level="ERROR")

    def _convert(self, fritz_xml_bytes):
        """
        Converts FRITZ!Box phonebook XML to MicroSIP contacts.xml format.

        FRITZ!Box schema (simplified):
            <phonebooks><phonebook>
              <contact>
                <person><realName>Full Name</realName></person>
                <telephony>
                  <number type="home|work|mobile" prio="0|1">0721...</number>
                </telephony>
              </contact>
            </phonebook></phonebooks>

        MicroSIP schema (all data as XML attributes, not child elements):
            <contacts refresh="0" silent="0">
              <contact name="Full Name" number="0721..." firstname=""
                       lastname="" phone="" mobile="" email="" address=""
                       city="" state="" zip="" comment=""
                       presence="0" starred="0" info=""/>
            </contacts>

        Mapping:
            realName       → name
            prio=1 number  → number  (primary, shown in search)
            2nd number     → phone
            3rd number     → mobile
            (4th+ dropped — MicroSIP has no further number fields)
        """
        fritz_root = ET.fromstring(fritz_xml_bytes)
        microsip_root = ET.Element("contacts")
        # refresh="0": MicroSIP will not auto-refresh (file is updated server-side)
        # silent="0":  MicroSIP will not suppress notifications
        microsip_root.set("refresh", "0")
        microsip_root.set("silent", "0")
        count = 0

        for contact in fritz_root.iter("contact"):
            # Skip contacts without a name
            name_el = contact.find("person/realName")
            if name_el is None or not name_el.text:
                continue
            name = name_el.text.strip()

            # Skip contacts without a telephony section
            telephony = contact.find("telephony")
            if telephony is None:
                continue

            # Collect numbers; the entry marked prio="1" goes first
            prio_num = None
            other_nums = []
            for num_el in telephony.findall("number"):
                num = (num_el.text or "").strip()
                if not num:
                    continue
                if num_el.get("prio") == "1":
                    prio_num = num
                else:
                    other_nums.append(num)

            numbers = ([prio_num] if prio_num else []) + other_nums
            if not numbers:
                self._debug(f"Skipping '{name}': no phone numbers")
                continue

            # Build the MicroSIP <contact ... /> element
            c = ET.SubElement(microsip_root, "contact")
            c.set("name",      name)
            c.set("number",    numbers[0])                              # primary
            c.set("firstname", "")
            c.set("lastname",  "")
            c.set("phone",     numbers[1] if len(numbers) > 1 else "")  # 2nd
            c.set("mobile",    numbers[2] if len(numbers) > 2 else "")  # 3rd
            c.set("email",     "")
            c.set("address",   "")
            c.set("city",      "")
            c.set("state",     "")
            c.set("zip",       "")
            c.set("comment",   "")
            c.set("presence",  "0")
            c.set("starred",   "0")
            c.set("info",      "")

            count += 1
            self._debug(f"  Contact: {name} → {numbers[:3]}")

        self.log(f"FritzPhonebook: converted {count} contacts.")

        # Compact output (no indentation) to match MicroSIP's expected format
        return (
            b'<?xml version="1.0" encoding="utf-8"?>'
            + ET.tostring(microsip_root, encoding="unicode").encode("utf-8")
        )

    def _debug(self, msg):
        """Logs a debug message only when DEBUG = True."""
        if DEBUG:
            self.log(f"[DEBUG] {msg}")
