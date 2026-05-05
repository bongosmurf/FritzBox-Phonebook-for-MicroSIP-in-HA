# fritz_phonebook – FritzBox Phonebook → Home Assistant → MicroSIP

An [AppDaemon](https://appdaemon.readthedocs.io/) app for [Home Assistant](https://www.home-assistant.io/) that reads the [AVM FRITZ!Box](https://fritz.com/) phonebook via TR-064 and writes a [MicroSIP](https://www.microsip.org/)-compatible `contacts.xml`, served directly by Home Assistant's built-in HTTP server.

## How it works

```
FRITZ!Box TR-064 API
       ↓
  AppDaemon app  (daily at 04:30, and on every restart)
       ↓
  /config/www/microsip_contacts.xml
       ↓
  http://<HA-IP>:8123/local/microsip_contacts.xml
       ↓
  MicroSIP  (Contacts URL setting)
```

1. AppDaemon calls `GetPhonebook` via TR-064 → FRITZ!Box returns a temporary download URL.
2. The app downloads the phonebook XML, converts it to MicroSIP's attribute-based `contacts.xml` format, and writes it to `/config/www/`.
3. Home Assistant serves the file without authentication under `/local/`.
4. MicroSIP fetches the file from that URL on startup (and on manual refresh).

## Requirements

- Home Assistant OS or Supervised with the **AppDaemon 4** add-on installed
- **fritzconnection** Python package (configured via the AppDaemon add-on, see below)
- AVM FRITZ!Box with FRITZ!OS ≥ 7.x
- TR-064 enabled on the FRITZ!Box:
  `Heimnetz → Netzwerkeinstellungen → Zugriff für Anwendungen zulassen`
- A FRITZ!Box user account with the **„FRITZ!Box-Einstellungen"** permission

## Installation

### 1. Add `fritzconnection` to AppDaemon

In the AppDaemon add-on configuration (HA UI → Settings → Add-ons → AppDaemon → Configuration tab):

```yaml
python_packages:
  - fritzconnection
```

Restart the AppDaemon add-on after saving.

### 2. Copy the app file

Copy `fritz_phonebook.py` to your AppDaemon apps directory:

```
/config/appdaemon/apps/fritz_phonebook.py
```

### 3. Add credentials to secrets.yaml

In `/config/secrets.yaml`:

```yaml
fritz_user: "your_fritzbox_username"
fritz_password: "your_fritzbox_password"
```

The user account can be the same one used for the FRITZ!Box Tools integration in Home Assistant.

### 4. Register the app

Add the following block to `/config/appdaemon/apps/apps.yaml`:

```yaml
fritz_phonebook:
  module: fritz_phonebook
  class: FritzPhonebook
  fritz_ip: "192.168.x.x"          # Your FRITZ!Box IP
  fritz_user: !secret fritz_user
  fritz_password: !secret fritz_password
  phonebook_id: 0                   # 0 = default phonebook
  output_path: "/config/www/microsip_contacts.xml"
  update_time: "04:30:00"           # Daily sync time (HH:MM:SS)
```

AppDaemon hot-reloads the app automatically after saving — no restart required.

### 5. Configure MicroSIP

In MicroSIP: **Settings → Contacts URL**:

```
http://<HA-IP>:8123/local/microsip_contacts.xml
```

Replace `<HA-IP>` with your Home Assistant's local IP address.

> **Note:** The `/local/` path in Home Assistant is served **without authentication**. The file is accessible to anyone who knows the URL on your local network. Do not expose port 8123 to the internet if this is a concern.

## Phonebook field mapping

| FRITZ!Box XML | MicroSIP attribute | Notes |
|---|---|---|
| `realName` | `name` | Full display name |
| `number` with `prio="1"` | `number` | Primary number (used for search/dialling) |
| 2nd number | `phone` | |
| 3rd number | `mobile` | |
| 4th+ numbers | — | Dropped (MicroSIP has no further fields) |

## Configuration reference

| Parameter | Required | Default | Description |
|---|---|---|---|
| `fritz_ip` | ✅ | — | IP address of your FRITZ!Box |
| `fritz_user` | ✅ | — | FRITZ!Box username |
| `fritz_password` | ✅ | — | FRITZ!Box password |
| `phonebook_id` | ❌ | `0` | ID of the phonebook to export (0 = default) |
| `output_path` | ✅ | — | Full path to write `contacts.xml` |
| `update_time` | ❌ | `04:30:00` | Daily sync time in `HH:MM:SS` format |

## Troubleshooting

**No contacts appear in MicroSIP**
- Check that the file was actually created at `output_path`.
- Verify the URL is reachable in a browser: `http://<HA-IP>:8123/local/microsip_contacts.xml`
- Open the file and confirm it contains `<contact ... />` entries.

**AppDaemon log shows an error**
- Enable debug output by setting `DEBUG = True` at the top of `fritz_phonebook.py`. Check the AppDaemon log (HA UI → Settings → Add-ons → AppDaemon → Log tab). Set `DEBUG` back to `False` afterwards.

**Authentication errors**
- As of FRITZ!OS 7.24, an explicit username is required. Make sure `fritz_user` is set to a valid FRITZ!Box user account, not left empty.
- Verify TR-064 is enabled on the FRITZ!Box (see Requirements above).

**`fritzconnection` not found**
- Confirm the package is listed under `python_packages` in the AppDaemon add-on configuration and that the add-on was restarted after the change.

## File paths reference

| Path (HA File Editor / HA CLI) | Description |
|---|---|
| `/config/appdaemon/apps/fritz_phonebook.py` | App source file |
| `/config/appdaemon/apps/apps.yaml` | App registration |
| `/config/secrets.yaml` | Credentials |
| `/config/www/microsip_contacts.xml` | Generated output file |

## License

MIT License – Copyright (c) 2026 Michael Ionescu
